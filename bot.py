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
# WARNING: Hardcoding a token is a security risk. Use os.getenv('BOT_TOKEN') for production.
BOT_TOKEN = "8377696674:AAEoN1aHOBf6NoKL3LizDyLdW6mgVcTPRCY"
API_HASH = os.getenv('API_HASH')
SESSION_STRING = os.getenv('PYROGRAM_SESSION')
SESSION_NAME = "dlight_scanner_bot"
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
    match = re.search(r"(?:https?://)?(?:www\.)?t\.me/(?:joinchat/|\+)?([\w-]+)", link)
    if not match:
        if link.startswith('@'):
            return link
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
        members_iterator = user_client.get_chat_members(entity.id, limit=200) 
        real_count = bot_count = suspicious_count = fake_count = 0
        total_members_scanned = 0

        async for member in members_iterator:
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

        member_total = getattr(entity, "members_count", "unknown")
        safe_title = escape_markdown(entity.title, version=2)

        report = (
            f"📊 *Member Analysis Report*\n\n"
            f"🏷 *Entity:* {safe_title}\n"
            f"👥 *Total Members Scanned:* {total_members_scanned} \\(out of {member_total}\\)\n\n"
            f"✅ *Real Users:* {real_count} \\({real_count/total_members_scanned*100:.1f}%\\)\n"
            f"🤖 *Bots:* {bot_count} \\({bot_count/total_members_scanned*100:.1f}%\\)\n"
            f"⚠️ *Suspicious Accounts:* {suspicious_count} \\({suspicious_count/total_members_scanned*100:.1f}%\\)\n"
            f"❌ *Fake Accounts:* {fake_count} \\({fake_count/total_members_scanned*100:.1f}%\\)\n\n"
            f"💡 *Note:* This analysis scans the first 200 members for quick estimation\\. Results are heuristic\\."
        )
        
        await processing_msg.edit_text(report, parse_mode="MarkdownV2")
            
    except errors.UsernameNotOccupied:
        safe_entity_id = escape_markdown(entity_id, version=2)
        await processing_msg.edit_text(f"❌ The username `{safe_entity_id}` does not exist\\.", parse_mode="MarkdownV2")
    except Exception as e:
        logger.error(f"Error scanning members: {e}")
        await processing_msg.edit_text("❌ An error occurred while scanning. The group may be private, or the link is invalid.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /start command."""
    welcome_text = (
        "👋 *Welcome to DLight \\- Member Scanner Bot\\!*\n\n"
        "I can analyze public Telegram groups and channels to estimate the number of real, fake, and bot accounts\\.\n\n"
        "*How to use:*\n"
        "Send me the link to any public group or channel\\.\n\n"
        "➡️ *Example:* `https://t\\.me/durov`\n\n"
        "_Created by Michael A\\. \\(Arewa\\)_"
    )
    await update.message.reply_text(welcome_text, parse_mode="MarkdownV2")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors caused by updates."""
    logger.error(f"Update {update} caused error {context.error}")

async def main():
    """Start the bot."""
    print("--- DLight Bot Starting ---")
    
    if not all([BOT_TOKEN, API_ID, API_HASH, SESSION_STRING]):
        print("FATAL: Missing one or more environment variables.")
        logger.error("FATAL: Missing BOT_TOKEN, API_ID, API_HASH, or PYROGRAM_SESSION. Or API_ID is invalid.")
        return
    
    global user_client
    user_client = Client(
        name=SESSION_NAME,
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=SESSION_STRING
    )
    
    try:
        await user_client.start()
        
        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, scan_members))
        application.add_error_handler(error_handler)
        
        print("🤖 Bot is running...")
        try:
            await application.run_polling()
        finally:
            # This ensures the user client is stopped when the bot stops.
            print("Shutting down user client...")
            await user_client.stop()

    except Exception as e:
        print(f"FATAL: A critical error occurred during startup: {e}")
        logger.error(f"FATAL: Failed to start. Error: {e}")
        try:
            if user_client:
                await user_client.stop()
        except Exception:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutting down.")

