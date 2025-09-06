import asyncio
import logging
import re
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pyrogram import Client, errors

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
# Load sensitive credentials from environment variables for security.
# These are set in the Render dashboard, NOT here in the code.
BOT_TOKEN = os.getenv('BOT_TOKEN')
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
SESSION_NAME = "dlight_scanner_bot"
# --- END CONFIGURATION ---


# Initialize Pyrogram client
# We will start it inside the main function after checking credentials.
pyro_client = None

async def extract_entity_info(link: str):
    """Extract entity username or joinchat id from link"""
    # This regex handles public channels/groups and private invite links
    match = re.search(r"t\.me/(?:joinchat/|\+)?([\w-]+)", link)
    if not match:
        # Fallback for simple @username mentions
        if link.startswith('@'):
            return link
        return None
    return match.group(1)

async def enhanced_analyze_member(user):
    """Enhanced member analysis with multiple checks to identify fake/suspicious accounts."""
    if getattr(user, "is_bot", False) or getattr(user, "bot", False):
        return "bot"
    
    suspicious_patterns = 0
    
    # 1. No profile photo is a common indicator
    if not getattr(user, "photo", None):
        suspicious_patterns += 1
    
    # 2. Suspicious username (e.g., many numbers, random chars)
    username = getattr(user, "username", "")
    if username and (re.search(r"\d{7,}", username) or len(username) > 25):
        suspicious_patterns += 1
    
    # 3. Suspicious first/last name patterns
    first_name = getattr(user, "first_name", "")
    last_name = getattr(user, "last_name", "")
    
    # Names with only emojis, special characters, or mixed random chars/numbers
    if first_name and (re.match(r"^[\W_]+$", first_name) or re.search(r"[a-zA-Z]+\d{4,}", first_name)):
        suspicious_patterns += 1
    
    # 4. No last name is common but less strong, so we give it less weight
    if not last_name:
        suspicious_patterns += 0.5
    
    # Final verdict based on the number of suspicious flags
    if suspicious_patterns >= 3:
        return "fake"
    elif suspicious_patterns >= 1.5:
        return "suspicious"
    
    return "real"

async def scan_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan group/channel members when a link is sent."""
    message = update.message
    user_input = message.text.strip()
    
    if not ("t.me/" in user_input or user_input.startswith('@')):
        await message.reply_text("❌ Please provide a valid Telegram group/channel link or username (e.g., `https://t.me/durov` or `@durov`).")
        return
    
    processing_msg = await message.reply_text("🔄 Scanning members... This may take a while for large groups.")
    
    entity_id = await extract_entity_info(user_input)
    if not entity_id:
        await processing_msg.edit_text("❌ Invalid Telegram link format.")
        return
    
    try:
        entity = await pyro_client.get_chat(entity_id)
        
        # Limit scan to 200 members for performance. Remove for full scan.
        members_iterator = pyro_client.get_chat_members(entity.id, limit=200) 
        
        real_count, bot_count, suspicious_count, fake_count = 0, 0, 0, 0
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
            await processing_msg.edit_text("❌ Could not retrieve any members. The bot might need to be an admin in the channel.")
            return

        # Generate report
        report = (
            f"📊 **Member Analysis Report**\n\n"
            f"🏷 **Entity:** {entity.title}\n"
            f"👥 **Total Members Scanned:** {total_members_scanned} (out of {entity.members_count})\n\n"
            f"✅ **Real Users:** {real_count} ({real_count/total_members_scanned*100:.1f}%)\n"
            f"🤖 **Bots:** {bot_count} ({bot_count/total_members_scanned*100:.1f}%)\n"
            f"⚠️ **Suspicious Accounts:** {suspicious_count} ({suspicious_count/total_members_scanned*100:.1f}%)\n"
            f"❌ **Fake Accounts:** {fake_count} ({fake_count/total_members_scanned*100:.1f}%)\n\n"
            f"💡 **Note:** This analysis is a heuristic estimation. The bot scans the first 200 members for a quick analysis."
        )
        
        await processing_msg.edit_text(report, parse_mode="Markdown")
            
    except errors.UserNotParticipant:
        await processing_msg.edit_text("❌ The bot must be a member of the group/channel to scan it.")
    except errors.ChatAdminRequired:
        await processing_msg.edit_text("❌ The bot must be an admin in this chat to see all members.")
    except Exception as e:
        logger.error(f"Error scanning members: {e}")
        await processing_msg.edit_text(f"❌ An error occurred while scanning. Please check the link and the bot's permissions.\n\n`Error: {e}`")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for the /start command."""
    welcome_text = (
        "👋 **Welcome to DLight - Member Scanner Bot!**\n\n"
        "I can analyze public Telegram groups and channels to estimate the number of real, fake, and bot accounts.\n\n"
        "**How to use:**\n"
        "1. For public groups/channels, just send me the link.\n"
        "2. For private groups/channels, I must be a member (preferably an admin) to see the users.\n\n"
        "➡️ Send a link to get started (e.g., `https://t.me/durov`).\n\n"
        "*Created by Michael A. (Arewa)*"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors caused by updates."""
    logger.error(f"Update {update} caused error {context.error}")

async def main():
    """Start the bot."""
    # --- Credentials Check ---
    if not all([BOT_TOKEN, API_ID, API_HASH]):
        logger.error("FATAL: Missing one or more environment variables (BOT_TOKEN, API_ID, API_HASH).")
        logger.error("Please check your configuration on Render.")
        return
    # --- End Credentials Check ---
    
    global pyro_client
    pyro_client = Client(
        name=SESSION_NAME,
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        in_memory=True  # Important for ephemeral filesystems like Render
    )
    
    await pyro_client.start()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, scan_members))
    application.add_error_handler(error_handler)
    
    logger.info("🤖 DLight Bot is now running!")
    await application.run_polling()
    
    await pyro_client.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shutting down.")

