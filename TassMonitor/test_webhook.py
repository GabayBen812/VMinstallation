#!/usr/bin/env python3
"""Quick test script to verify Discord webhook URLs."""
import sys
import requests

def test_webhook(webhook_url: str):
    """Test a Discord webhook URL."""
    print(f"Testing webhook: {webhook_url[:50]}...")
    
    try:
        payload = {
            "content": "🔧 Webhook test - if you see this, the webhook is working!",
            "username": "Webhook Tester"
        }
        resp = requests.post(webhook_url, json=payload, timeout=10)
        
        print(f"Status Code: {resp.status_code}")
        print(f"Response: {resp.text[:200]}")
        
        if resp.status_code in (200, 204):
            print("✅ Webhook is working!")
            return True
        elif resp.status_code == 401:
            print("❌ ERROR: 401 Unauthorized - Invalid webhook token")
            print("   The webhook URL is invalid or expired. Create a new webhook in Discord.")
            return False
        elif resp.status_code == 404:
            print("❌ ERROR: 404 Not Found - Webhook doesn't exist")
            print("   The webhook may have been deleted. Create a new webhook in Discord.")
            return False
        else:
            print(f"❌ ERROR: Unexpected status code {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ ERROR: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_webhook.py <webhook_url>")
        print("\nExample:")
        print("  python3 test_webhook.py https://discord.com/api/webhooks/...")
        sys.exit(1)
    
    webhook_url = sys.argv[1]
    success = test_webhook(webhook_url)
    sys.exit(0 if success else 1)

