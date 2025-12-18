"""
Discord Bot - Handles commands for managing keywords.
"""
import os
import asyncio
from typing import Optional
import discord
from discord.ext import commands
from keywords_manager import get_keywords_manager


class KeywordsBot(commands.Bot):
    """Discord bot for managing keywords."""
    
    def __init__(self, command_prefix: str = "!"):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.keywords_manager = get_keywords_manager()
    
    async def setup_hook(self):
        """Called when the bot is starting up."""
        print("Discord bot starting up...")
    
    async def on_ready(self):
        """Called when the bot is ready."""
        print(f"Discord bot logged in as {self.user}")
        print(f"Bot ID: {self.user.id}")
    
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Handle command errors."""
        if isinstance(error, commands.CommandNotFound):
            return  # Ignore unknown commands
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing required argument: {error.param.name}")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ Command is on cooldown. Try again in {error.retry_after:.1f} seconds.")
        else:
            await ctx.send(f"❌ Error: {str(error)}")
            print(f"Command error: {error}")


def setup_bot_commands(bot: KeywordsBot):
    """Set up bot commands."""
    
    @bot.command(name="poly")
    async def poly_command(ctx: commands.Context, subcommand: Optional[str] = None):
        """
        Main command handler for !poly commands.
        Usage: !poly setkeywords [with .txt file attachment]
        """
        if subcommand is None:
            await ctx.send("📋 Available commands:\n"
                          "  `!poly setkeywords` - Update keywords from attached .txt file\n"
                          "  `!poly listkeywords` - List current keywords\n"
                          "  `!poly help` - Show this help message")
            return
        
        if subcommand == "help":
            await ctx.send("📋 **Poly Keywords Manager**\n\n"
                          "**Commands:**\n"
                          "  `!poly setkeywords` - Attach a .txt file with keywords (one per line) to update the keyword list\n"
                          "  `!poly listkeywords` - Show the current list of keywords\n"
                          "  `!poly help` - Show this help message\n\n"
                          "**Example:**\n"
                          "1. Create a .txt file with keywords (one per line)\n"
                          "2. Use `!poly setkeywords` and attach the file\n"
                          "3. The bot will update the keywords in Supabase")
            return
        
        if subcommand == "listkeywords":
            keywords = bot.keywords_manager.load_keywords()
            if not keywords:
                await ctx.send("❌ No keywords found.")
                return
            
            # Discord message limit is 2000 characters
            keywords_text = "\n".join(f"  • {kw}" for kw in keywords)
            if len(keywords_text) > 1900:
                # Split into multiple messages if needed
                chunks = []
                current_chunk = "📋 **Current Keywords:**\n"
                for kw in keywords:
                    line = f"  • {kw}\n"
                    if len(current_chunk) + len(line) > 1900:
                        chunks.append(current_chunk)
                        current_chunk = "📋 **Current Keywords (continued):**\n" + line
                    else:
                        current_chunk += line
                if current_chunk:
                    chunks.append(current_chunk)
                
                for chunk in chunks:
                    await ctx.send(chunk)
            else:
                await ctx.send(f"📋 **Current Keywords ({len(keywords)} total):**\n{keywords_text}")
            return
        
        if subcommand == "setkeywords":
            # Check if message has attachments
            if not ctx.message.attachments:
                await ctx.send("❌ Please attach a .txt file with keywords (one per line).\n"
                              "Usage: `!poly setkeywords` [attach .txt file]")
                return
            
            # Find .txt attachment
            txt_attachment = None
            for attachment in ctx.message.attachments:
                if attachment.filename.lower().endswith('.txt'):
                    txt_attachment = attachment
                    break
            
            if not txt_attachment:
                await ctx.send("❌ No .txt file found in attachments. Please attach a .txt file.")
                return
            
            # Download and parse the file
            try:
                # Download the file
                file_content = await txt_attachment.read()
                content_text = file_content.decode('utf-8')
                
                # Parse keywords (one per line, strip whitespace, filter empty lines)
                keywords = []
                for line in content_text.split('\n'):
                    keyword = line.strip()
                    if keyword and not keyword.startswith('#'):  # Ignore empty lines and comments
                        keywords.append(keyword)
                
                if not keywords:
                    await ctx.send("❌ No valid keywords found in the file. Please provide keywords (one per line).")
                    return
                
                # Update keywords in Supabase
                await ctx.send(f"⏳ Processing {len(keywords)} keywords...")
                success = bot.keywords_manager.update_keywords(keywords)
                
                if success:
                    # Invalidate cache to force reload
                    bot.keywords_manager.invalidate_cache()
                    await ctx.send(f"✅ Successfully updated keywords! ({len(keywords)} keywords)\n"
                                  f"📝 New keywords will be used for @everyone tagging from now on.")
                else:
                    await ctx.send("❌ Failed to update keywords. Please check the logs for errors.")
                    
            except UnicodeDecodeError:
                await ctx.send("❌ Error: File must be UTF-8 encoded.")
            except Exception as e:
                await ctx.send(f"❌ Error processing file: {str(e)}")
                print(f"Error processing keywords file: {e}")
            return
        
        # Unknown subcommand
        await ctx.send(f"❌ Unknown subcommand: `{subcommand}`\n"
                      f"Use `!poly help` for available commands.")


async def run_bot(bot_token: str):
    """Run the Discord bot."""
    bot = KeywordsBot(command_prefix="!")
    setup_bot_commands(bot)
    
    try:
        await bot.start(bot_token)
    except discord.LoginFailure:
        print("ERROR: Invalid Discord bot token")
    except Exception as e:
        print(f"ERROR: Failed to start Discord bot: {e}")


def start_bot_background(bot_token: str):
    """Start the Discord bot in a background task."""
    if not bot_token:
        print("WARNING: DISCORD_BOT_TOKEN not set, Discord bot commands will not be available")
        return None
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    def run():
        loop.run_until_complete(run_bot(bot_token))
    
    import threading
    bot_thread = threading.Thread(target=run, daemon=True)
    bot_thread.start()
    return bot_thread

