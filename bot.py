import asyncio
import logging
import re
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pyrogram import Client, errors
from telegram.helpers import escape_markdown

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv('BOT_TOKEN')
API_HASH = os.getenv('API_HASH')
API_ID = None
# Safely get and convert API_ID to an integer
try:
    API_ID_STR = os.getenv('API_ID')
    if API_ID_STR:
        API_ID = int(API_ID_STR)
except (ValueError, TypeError):
    logger.error("FATAL: API_ID environment variable is not a valid number.")
# --- END CONFIGURATION ---

user_client = None

async def extract_entity_info(link: str):
    """Extract entity username or joinchat id from link"""
    # This regex is improved to handle public channel links like t.me/channelname
    match = re.search(r"(?:https?://)?t\.me/(?:joinchat/|\+)?([\w-]+)", link)
    if not match:
        if link.startswith('@'):
            return link[1:]  # Remove the @ symbol
        return None
    return match.group(1)

async def enhanced_analyze_member(user):
    """Enhanced member analysis with multiple heuristics."""
    if getattr(user, "is_bot", False) or getattr(user, "bot", False):
        return "bot"
    
    suspicious_patterns = 0
    if not getattr(user, "photo", None):
        suspicious_patterns += 1
    
    username = getattr(user, "username", "")
    if username and (re.search(r"\d{7,}", username) or len(username) > 25):
        suspicious_patterns += 1
    
    first_name = getattr(user, "first_name", "")
    last_name = getattr(user, "last_name", "")
    
    if first_name and (re.match(r"^[\W_]+$", first_name) or re.search(r"[a-zA-Z]+\d{4,}", first_name)):
        suspicious_patterns += 1
    
    if not last_name:
        suspicious_patterns += 1
    
    if suspicious_patterns >= 3:
        return "fake"
    elif suspicious_patterns >= 2:
        return "suspicious"
    
    return "real"

async def scan_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan group/channel members when a link is sent."""
    message = update.message
    user_input = message.text.strip()
    
    if not ("t.me/" in user_input or user_input.startswith('@')):
        await message.reply_text(
            "❌ Please provide a valid Telegram group/channel link or username\.\n\n*Example:* `https://t\.me/durov` or `@durov`",
            parse_mode="MarkdownV2"
        )
        return
    
    processing_msg = await message.reply_text("🔄 Scanning members... This may take a while for large groups.")
    
    entity_id = await extract_entity_info(user_input)
    if not entity_id:
        await processing_msg.edit_text("❌ Invalid Telegram link format.")
        return
    
    try:
        entity = await user_client.get_chat(entity_id)
        
        # Check if we can access members
        try:
            # Try to get a small number of members first to test access
            test_members = []
            async for member in user_client.get_chat_members(entity.id, limit=5):
                test_members.append(member)
                
            if not test_members:
                await processing_msg.edit_text("❌ Could not retrieve any members. The bot might not have access.")
                return
                
        except errors.ChatAdminRequired:
            await processing_msg.edit_text("❌ Bot needs admin permissions to view members.")
            return
        except errors.ChannelPrivate:
            await processing_msg.edit_text("❌ This is a private channel/group. I need to be a member to scan it.")
            return
            
        # Now scan all available members (up to 200)
        real_count = bot_count = suspicious_count = fake_count = 0
        total_members_scanned = 0

        async for member in user_client.get_chat_members(entity.id, limit=200):
            total_members_scanned += 1
            user_type = await enhanced_analyze_member(member.user)
            if user_type == "real":
                real_count += 1
            elif user_type == "bot":
                bot_count += 1
            elif user_type == "fake":
                fake_count += 1
            else:
                suspicious_count += 1
        
        if total_members_scanned == 0:
            await processing_msg.edit_text("❌ Could not retrieve any members. The bot might not have access, or the chat is empty.")
            return

        member_total = getattr(entity, "members_count", total_members_scanned)
        # Escape the title for MarkdownV2
        safe_title = escape_markdown(entity.title, version=2)

        report = (
            f"📊 *Member Analysis Report*\n\n"
            f"🏷 *Entity:* {safe_title}\n"
            f"👥 *Total Members Scanned:* {total_members_scanned} \(out of {member_total}\)\n\n"
            f"✅ *Real Users:* {real_count} \({real_count/total_members_scanned*100:.1f}%\)\n"
            f"🤖 *Bots:* {bot_count} \({bot_count/total_members_scanned*100:.1f}%\)\n"
            f"⚠️ *Suspicious Accounts:* {suspicious_count} \({suspicious_count/total_members_scanned*100:.1f}%\)\n"
            f"❌ *Fake Accounts:* {fake_count} \({fake_count/total_members_scanned*100:.1f}%\)\n\n"
            f"💡 *Note:* This analysis scans the first 200 members for quick estimation\. Results are heuristic\."
        )
        
        await processing_msg.edit_text(report, parse_mode="MarkdownV2")
            
    except errors.UsernameNotOccupied:
        await processing_msg.edit_text(f"❌ The username `{entity_id}` does not exist.")
    except errors.ChannelInvalid:
        await processing_msg.edit_text("❌ Invalid channel/group. Please check the link.")
    except errors.ChatAdminRequired:
        await processing_msg.edit_text("❌ Bot needs admin permissions to view members.")
    except errors.ChannelPrivate:
        await processing_msg.edit_text("❌ This is a private channel/group. I need to be a member to scan it.")
    except Exception as e:
        logger.error(f"Error scanning members: {e}")
        await processing_msg.edit_text("❌ An error occurred while scanning. Please try again later.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /start command."""
    welcome_text = (
        "👋 *Welcome to DLight \- Member Scanner Bot\!*\n\n"
        "I can analyze public Telegram groups and channels to estimate the number of real, fake, and bot accounts\.\n\n"
        "*How to use:*\n"
        "Send me the link to any public group or channel\.\n\n"
        "➡️ *Example:* `https://t\.me/durov`\n\n"
        "_Created by Michael A\. \(Arewa\)_"
    )
    await update.message.reply_text(welcome_text, parse_mode="MarkdownV2")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /help command."""
    help_text = (
        "📖 *DLight Help Guide*\n\n"
        "*Commands:*\n"
        "/start \- Start the bot\n"
        "/help \- Show this help message\n\n"
        "*Usage:*\n"
        "1\. Add the bot as admin to your group/channel\n"
        "2\. Send the group/channel link to the bot\n"
        "3\. Wait for the analysis to complete\n\n"
        "*Note:* For large groups, the scan may take several minutes\.\n\n"
        "⚠️ *Limitations:*\n"
        "• The bot needs admin permissions\n"
        "• Analysis is heuristic\-based\n"
        "• Private groups require bot membership\n\n"
        "🔧 *Bot by:* @dlight | *Creator:* Michael A\. \(Arewa\)"
    )
    await update.message.reply_text(help_text, parse_mode="MarkdownV2")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors caused by updates."""
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text("❌ An error occurred. Please try again later.")

async def main():
    """Start the bot."""
    print("--- DLight Bot Starting ---")
    
    if not all([BOT_TOKEN, API_ID, API_HASH]):
        print("FATAL: Missing one or more environment variables.")
        logger.error("FATAL: Missing BOT_TOKEN, API_ID, or API_HASH.")
        return
    
    global user_client
    # Create a user client using bot token (no session string needed)
    user_client = Client(
        name="dlight_scanner",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        in_memory=True  # No need to save session to file
    )
    
    try:
        await user_client.start()
        print("✅ User client started successfully")
        
        # Check if the client is authorized
        me = await user_client.get_me()
        print(f"✅ Logged in as: {me.first_name} (@{me.username})")
        
        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, scan_members))
        application.add_error_handler(error_handler)
        
        print("🤖 Bot is running...")
        print("🔧 Created by Michael A. (Arewa)")
        
        try:
            await application.run_polling()
        finally:
            # This ensures the user client is stopped when the bot stops.
            print("Shutting down user client...")
            await user_client.stop()

    except errors.ApiIdInvalid:
        print("FATAL: API ID is invalid.")
    except errors.AccessTokenInvalid:
        print("FATAL: Bot token is invalid.")
    except Exception as e:
        print(f"FATAL: A critical error occurred during startup: {e}")
        logger.error(f"FATAL: Failed to start. Error: {e}")
        if user_client and user_client.is_connected:
            await user_client.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutting down.")
