import os
import sys
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple

import requests
from bs4 import BeautifulSoup

try:
    # Prefer deep_translator for reliability
    from deep_translator import GoogleTranslator  # type: ignore
except Exception as import_error:  # pragma: no cover - fallback import guard
    print(f"WARNING: Failed to import GoogleTranslator: {import_error}")
    print("  Install with: pip install deep-translator")
    GoogleTranslator = None  # type: ignore

from keywords_manager import get_keywords_manager
from discord_bot import start_bot_background


# Channels to monitor (add more as needed)
# Each channel can specify which webhook to use via "webhook" field
# If not specified, defaults to the primary webhook (DISCORD_WEBHOOK_URL)
CHANNELS: List[Dict[str, str]] = [
    {"handle": "tass_agency", "display_name": "TASS"},
    {"handle": "Alarabiya", "display_name": "Al Arabiya"},
    {"handle": "Aljazeera", "display_name": "Al Jazeera"},
    {"handle": "nayaforiraq", "display_name": "OSINT"},
    {"handle": "news_kremlin_eng", "display_name": "Kremlin News"},
    # New channels with separate webhook
    {"handle": "gazaalannet", "display_name": "Gaza Al Annet", "webhook": "secondary"},
    {"handle": "channelnabatieh", "display_name": "Channel Nabatieh", "webhook": "secondary"},
    {"handle": "redlinkleb", "display_name": "Red Link Lebanon", "webhook": "secondary"},
]

# Keywords are now loaded dynamically from Supabase via KeywordsManager
# See keywords_manager.py for keyword storage and retrieval

# Channels that should have keyword alert detection
ALERT_CHANNELS = {"gazaalannet", "channelnabatieh", "redlinkleb"}

# Discord configuration
# Webhook is read from environment or from a local .env file at repository root.

# Polling configuration
SLEEP_SECONDS = 20
REQUEST_TIMEOUT = 20
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(BASE_DIR, "state")
os.makedirs(STATE_DIR, exist_ok=True)
APP_ROOT = os.path.dirname(BASE_DIR)


def load_env_from_file(env_path: str) -> None:
    """Minimal .env loader to support local runs (systemd loads it in prod).

    Only sets variables that are not already present in the environment.
    """
    try:
        if not os.path.isfile(env_path):
            return
        with open(env_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        # Non-fatal; proceed with whatever env is available
        pass


# Load .env for local runs (systemd uses EnvironmentFile for services)
load_env_from_file(os.path.join(APP_ROOT, ".env"))

# Resolve webhook URLs from environment
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
DISCORD_WEBHOOK_URL_2 = os.getenv("DISCORD_WEBHOOK_URL_2", "").strip()

def channel_public_feed(handle: str) -> str:
    return f"https://t.me/s/{handle}"


def channel_post_url(handle: str, post_id: int) -> str:
    return f"https://t.me/{handle}/{post_id}"


def read_last_post_id(handle: str) -> Optional[int]:
    state_file = os.path.join(STATE_DIR, f"last_post_id_{handle}.txt")
    if not os.path.exists(state_file):
        return None
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            value = f.read().strip()
            return int(value) if value else None
    except Exception:
        return None


def write_last_post_id(handle: str, post_id: int) -> None:
    state_file = os.path.join(STATE_DIR, f"last_post_id_{handle}.txt")
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            f.write(str(post_id))
    except Exception:
        pass


def fetch_channel_messages(session: requests.Session, handle: str) -> List[Dict[str, str]]:
    """
    Scrape the public Telegram channel page and return a list of messages.
    Each item contains: {"id": str, "text": str, "url": str, "has_image": bool}
    """
    response = session.get(channel_public_feed(handle), headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    messages = []

    for msg_div in soup.select(".tgme_widget_message_wrap"):
        container = msg_div.find("div", class_="tgme_widget_message")
        if not container:
            continue

        data_post = container.get("data-post")  # e.g., "handle/123456"
        if not data_post or "/" not in data_post:
            continue

        try:
            post_id_str = data_post.split("/")[-1]
            post_id = int(post_id_str)
        except Exception:
            continue

        # Extract textual content (if any)
        text_block = container.find("div", class_="tgme_widget_message_text")
        # Ensure line breaks are preserved
        text = text_block.get_text("\n", strip=True) if text_block else ""

        # Check if message has images (photos, videos, etc.)
        # Look for common Telegram media elements
        has_image = bool(
            container.find("a", class_="tgme_widget_message_photo_wrap") or
            container.find("div", class_="tgme_widget_message_video_wrap") or
            container.find("div", class_="tgme_widget_message_document_wrap") or
            container.find("i", class_="tgme_widget_message_photo") or
            container.find("i", class_="tgme_widget_message_video")
        )

        messages.append(
            {
                "id": str(post_id),
                "text": text,
                "url": channel_post_url(handle, post_id),
                "has_image": has_image,
            }
        )

    # Deduplicate, sort by id ascending
    unique: Dict[int, Dict[str, str]] = {}
    for m in messages:
        try:
            pid = int(m["id"])
            unique[pid] = m
        except Exception:
            continue
    return [unique[k] for k in sorted(unique.keys())]


def translate_to_english(text: str) -> str:
    if not text:
        return ""
    if GoogleTranslator is None:
        print("WARNING: GoogleTranslator is not available (deep_translator import failed)")
        return text  # Fallback: return original if translator isn't available
    
    # Google Translate has a character limit (usually 5000), split if needed
    MAX_CHARS = 4500  # Leave some margin
    if len(text) > MAX_CHARS:
        # Split into chunks and translate separately
        chunks = []
        current_chunk = ""
        for line in text.split("\n"):
            if len(current_chunk) + len(line) + 1 > MAX_CHARS:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = line
            else:
                current_chunk += ("\n" if current_chunk else "") + line
        if current_chunk:
            chunks.append(current_chunk)
        
        # Translate each chunk
        translated_chunks = []
        for chunk in chunks:
            chunk_translation = translate_to_english(chunk)  # Recursive call for chunk
            translated_chunks.append(chunk_translation)
        return "\n".join(translated_chunks)
    
    # Retry logic for translation (sometimes Google Translate has temporary issues)
    max_retries = 3
    for attempt in range(max_retries):
        try:
            translator = GoogleTranslator(source="auto", target="en")
            translated = translator.translate(text)
            if translated and translated != text:
                return translated
            # If translation returned same text, might be an issue
            if attempt < max_retries - 1:
                time.sleep(1)  # Wait before retry
                continue
            return translated or text
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            if attempt < max_retries - 1:
                print(f"WARNING: Translation attempt {attempt + 1} failed: {error_msg}, retrying...")
                time.sleep(2)  # Wait before retry
            else:
                print(f"ERROR: Translation failed after {max_retries} attempts: {error_msg}")
                print(f"  Original text (first 100 chars): {text[:100]}...")
                return text
    return text


def shorten(text: str, limit: int = 1800) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 10].rstrip() + "\n[...]"


def send_to_discord(content: str, username: str = "Telegram Translate Monitor", webhook_url: Optional[str] = None) -> Tuple[bool, str]:
    """
    Send a message to Discord webhook.
    
    Args:
        content: Message content to send
        username: Username for the webhook message
        webhook_url: Optional webhook URL. If None, uses DISCORD_WEBHOOK_URL
    """
    target_webhook = webhook_url or DISCORD_WEBHOOK_URL
    if not target_webhook:
        return False, "No webhook URL provided"
    try:
        payload = {"content": content, "username": username}
        resp = requests.post(target_webhook, json=payload, timeout=REQUEST_TIMEOUT)
        if resp.status_code in (200, 204):
            return True, ""
        # Provide more detailed error information
        error_detail = resp.text[:200] if resp.text else "No response body"
        if resp.status_code == 401:
            return False, f"HTTP 401 Unauthorized - Invalid webhook token. The webhook URL may be expired or incorrect. Response: {error_detail}"
        elif resp.status_code == 404:
            return False, f"HTTP 404 Not Found - Webhook not found. The webhook may have been deleted. Response: {error_detail}"
        else:
            return False, f"HTTP {resp.status_code}: {error_detail}"
    except Exception as e:
        return False, f"Exception: {str(e)}"


def check_alert_keywords(text: str) -> bool:
    """
    Check if any alert keywords are present in the text (case-insensitive).
    Keywords are loaded dynamically from Supabase.
    
    Args:
        text: Text to check (can be original or translated)
    
    Returns:
        True if any keyword is found, False otherwise
    """
    if not text:
        return False
    text_lower = text.lower()
    keywords_manager = get_keywords_manager()
    keywords = keywords_manager.load_keywords()
    return any(keyword.lower() in text_lower for keyword in keywords)


def build_discord_message(channel_name: str, translated_text: str, post_url: str, tag_everyone: bool = False) -> str:
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    translated_preview = shorten(translated_text, 1800) if translated_text else "(no text)"

    parts = []
    
    # Add @everyone tag at the beginning if alert keywords detected
    if tag_everyone:
        parts.append("@everyone")
    
    parts.extend([
        f"📰 [{channel_name}] {translated_preview}",
        f"🔗 {post_url}",
        f"`{ts}`",
    ])
    message = "\n".join(parts)
    return shorten(message, 1900)


def initialize_last_seen(session: requests.Session, handle: str) -> Optional[int]:
    """On first run, set last seen to newest post to avoid backfilling spam.
    
    Returns:
        The last_seen post ID (existing or newly initialized)
        None if initialization failed
    """
    current = read_last_post_id(handle)
    if current is not None:
        # Already initialized, return existing value
        return current
    
    # First run: initialize to newest post without sending anything
    try:
        msgs = fetch_channel_messages(session, handle)
        if not msgs:
            return None
        newest_id = int(msgs[-1]["id"])  # messages sorted ascending
        write_last_post_id(handle, newest_id)
        print(f"Initialized {handle}: starting from post {newest_id} (no old messages will be sent)")
        return newest_id
    except Exception as e:
        print(f"Warning: Failed to initialize {handle}: {e}")
        return None


def process_new_messages(session: requests.Session, handle: str, display_name: str, webhook_url: Optional[str] = None) -> None:
    last_seen = read_last_post_id(handle)
    msgs = fetch_channel_messages(session, handle)
    if not msgs:
        return

    # Determine new messages strictly greater than last_seen
    if last_seen is None:
        # If we have no state, initialize to newest and skip sending
        initialize_last_seen(session, handle)
        return

    new_msgs = [m for m in msgs if int(m["id"]) > int(last_seen)]
    if not new_msgs:
        return

    # Send in chronological order
    for msg in new_msgs:
        original = msg.get("text", "").strip()
        has_image = msg.get("has_image", False)
        
        # For @redlinkleb: skip image-only messages (images with no text)
        if handle == "redlinkleb" and has_image and not original:
            print(f"SKIP: {handle} post {msg['id']} is image-only (no text), ignoring")
            # Still update last_post_id to avoid reprocessing
            write_last_post_id(handle, int(msg["id"]))
            continue
        
        translated = translate_to_english(original) if original else ""
        
        # Debug: Log translation status (only for non-English text to avoid spam)
        if original and translated and original != translated:
            # Show a preview of translation working
            orig_preview = original[:50].replace("\n", " ")
            trans_preview = translated[:50].replace("\n", " ")
            if orig_preview != trans_preview:
                print(f"TRANSLATE: {handle} post {msg['id']}: '{orig_preview}...' -> '{trans_preview}...'")
        
        # Check for alert keywords in the 3 new channels (check both original and translated)
        tag_everyone = False
        if handle in ALERT_CHANNELS:
            # Check both original and translated text for keywords
            if check_alert_keywords(original) or check_alert_keywords(translated):
                tag_everyone = True
                print(f"ALERT: {handle} post {msg['id']} contains alert keywords - tagging @everyone")
        
        content = build_discord_message(display_name, translated, msg["url"], tag_everyone=tag_everyone)
        ok, err = send_to_discord(content, webhook_url=webhook_url)
        if ok:
            alert_status = " (with @everyone)" if tag_everyone else ""
            print(f"OK: Sent {handle} post {msg['id']} to Discord{alert_status}")
            write_last_post_id(handle, int(msg["id"]))
        else:
            print(f"ERROR: Failed to send {handle} post {msg['id']}: {err}")


def main_loop() -> None:
    print("Starting Telegram -> Discord translate monitor (auto -> EN)...")
    print("Channels:")
    for ch in CHANNELS:
        webhook_type = ch.get("webhook", "primary")
        print(f"   - {ch['display_name']} (@{ch['handle']}) -> {channel_public_feed(ch['handle'])} [webhook: {webhook_type}]")

    # Validate configuration before proceeding
    if not DISCORD_WEBHOOK_URL or not DISCORD_WEBHOOK_URL.startswith("https://discord.com/api/webhooks/"):
        print("ERROR: Missing or invalid DISCORD_WEBHOOK_URL. Set it in environment or .env.")
        return
    
    # Validate secondary webhook if any channels use it
    channels_using_secondary = [ch for ch in CHANNELS if ch.get("webhook") == "secondary"]
    if channels_using_secondary:
        if not DISCORD_WEBHOOK_URL_2 or not DISCORD_WEBHOOK_URL_2.startswith("https://discord.com/api/webhooks/"):
            print("ERROR: Missing or invalid DISCORD_WEBHOOK_URL_2. Set it in environment or .env.")
            print(f"Channels requiring secondary webhook: {', '.join([ch['handle'] for ch in channels_using_secondary])}")
            return

    # Test translation functionality
    print("Testing translation service...")
    test_text = "مرحبا"  # Arabic for "hello"
    test_translation = translate_to_english(test_text)
    if test_translation == test_text:
        print("⚠️  WARNING: Translation test failed - translations may not work!")
        print("   The translator returned the original text instead of translating.")
        print("   Check if deep_translator is installed: pip install deep-translator")
    else:
        print(f"✅ Translation test passed: '{test_text}' -> '{test_translation}'")
    
    # Initialize keywords manager and load keywords
    keywords_manager = get_keywords_manager()
    keywords = keywords_manager.load_keywords()
    print(f"Loaded {len(keywords)} alert keywords (from Supabase or defaults)")

    # Start Discord bot for keyword management commands
    discord_bot_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if discord_bot_token:
        print("Starting Discord bot for keyword management...")
        bot_thread = start_bot_background(discord_bot_token)
        if bot_thread:
            print("Discord bot started successfully. Commands available: !poly setkeywords, !poly listkeywords")
    else:
        print("WARNING: DISCORD_BOT_TOKEN not set. Discord bot commands will not be available.")
        print("  Set DISCORD_BOT_TOKEN in .env to enable !poly commands for keyword management.")

    session = requests.Session()

    # Initialize on startup to avoid backfilling for all channels
    print("Initializing channels (setting baseline to prevent old message spam)...")
    for ch in CHANNELS:
        initialize_last_seen(session, ch["handle"])
    print("Initialization complete. Starting to monitor for NEW messages only.\n")

    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 5

    # Send simple startup message to Discord (only to primary webhook to avoid duplicate)
    startup_msg = "✅ Monitor started - monitoring for new messages only"
    hb_ok, hb_err = send_to_discord(startup_msg, username="Telegram Translate Monitor")
    if hb_ok:
        print("OK: Startup message sent to Discord")
    else:
        # Check if it's a webhook token error (non-critical, monitoring will still work)
        if "401" in hb_err or "Invalid Webhook Token" in hb_err or "Unauthorized" in hb_err:
            print("⚠️  WARNING: Webhook token appears invalid/expired.")
            print(f"   Error details: {hb_err}")
            print("   Update DISCORD_WEBHOOK_URL in .env with a valid webhook URL.")
            print("   Monitoring will continue, but messages won't be sent to Discord until fixed.")
        elif "404" in hb_err or "Not Found" in hb_err:
            print("⚠️  WARNING: Webhook not found (404).")
            print(f"   Error details: {hb_err}")
            print("   The webhook may have been deleted. Create a new webhook and update DISCORD_WEBHOOK_URL in .env.")
        else:
            print(f"⚠️  WARNING: Could not send startup message: {hb_err}")
            print("   Monitoring will continue, but messages may not be sent to Discord.")

    # Re-sync all channels one more time right before starting to ensure we don't send old messages
    # This handles any messages that might have arrived during initialization
    print("Final sync before monitoring starts...")
    for ch in CHANNELS:
        try:
            msgs = fetch_channel_messages(session, ch["handle"])
            if msgs:
                newest_id = int(msgs[-1]["id"])
                write_last_post_id(ch["handle"], newest_id)
        except Exception:
            pass  # Non-fatal, continue with existing state
    print("Ready to monitor. Only NEW messages will be sent.\n")

    while True:
        start = time.time()
        try:
            for ch in CHANNELS:
                # Determine which webhook to use for this channel
                webhook_type = ch.get("webhook", "primary")
                webhook_url = DISCORD_WEBHOOK_URL_2 if webhook_type == "secondary" else DISCORD_WEBHOOK_URL
                process_new_messages(session, ch["handle"], ch["display_name"], webhook_url=webhook_url)
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            print(f"ERROR during processing: {e}")
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                # Send an error alert to Discord to surface issues
                err_msg = f"Monitor encountered repeated errors (x{consecutive_errors}). Last error: {e}"
                send_to_discord(err_msg, username="Telegram Translate Monitor")
                consecutive_errors = 0
        finally:
            elapsed = time.time() - start
            # Keep overall loop cadence roughly SLEEP_SECONDS between full scans
            sleep_for = max(1, SLEEP_SECONDS - int(elapsed))
            time.sleep(sleep_for)


if __name__ == "__main__":
    # Self-test mode: send a test message and exit
    if "--self-test" in sys.argv:
        load_env_from_file(os.path.join(APP_ROOT, ".env"))
        DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        if not DISCORD_WEBHOOK_URL:
            print("❌ DISCORD_WEBHOOK_URL not set. Add it to .env or environment.")
            sys.exit(1)
        ok, err = send_to_discord("🔧 Self-test message from Telegram translate monitor", username="Telegram Translate Monitor")
        if ok:
            print("Self-test sent successfully")
            sys.exit(0)
        else:
            print(f"Self-test failed: {err}")
            sys.exit(2)
    
    # Self-test mode for secondary webhook: send a test message and exit
    if "--self-test-2" in sys.argv:
        load_env_from_file(os.path.join(APP_ROOT, ".env"))
        DISCORD_WEBHOOK_URL_2 = os.getenv("DISCORD_WEBHOOK_URL_2", "").strip()
        if not DISCORD_WEBHOOK_URL_2:
            print("❌ DISCORD_WEBHOOK_URL_2 not set. Add it to .env or environment.")
            sys.exit(1)
        ok, err = send_to_discord("🔧 Self-test message from Telegram translate monitor (secondary webhook)", username="Telegram Translate Monitor", webhook_url=DISCORD_WEBHOOK_URL_2)
        if ok:
            print("Self-test (secondary webhook) sent successfully")
            sys.exit(0)
        else:
            print(f"Self-test (secondary webhook) failed: {err}")
            sys.exit(2)

    try:
        main_loop()
    except KeyboardInterrupt:
        print("\nStopped by user")

