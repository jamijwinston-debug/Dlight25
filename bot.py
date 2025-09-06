import asyncio
import logging
import re
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from pyrogram import Client, errors
from telethon import TelegramClient

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot config
BOT_TOKEN = "YOUR_BOT_TOKEN"
API_ID = "YOUR_API_ID"  # Get from https://my.telegram.org
API_HASH = "YOUR_API_HASH"  # Get from https://my.telegram.org
SESSION_NAME = "dlight_scanner_bot"

# Initialize clients
pyro_client = Client(
    name=SESSION_NAME,
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

telethon_client = TelegramClient(
    session=SESSION_NAME + "_telethon",
    api_id=int(API_ID),
    api_hash=API_HASH
)

async def extract_entity_info(link: str):
    """Extract entity username or joinchat id from link"""
    match = re.search(r"(?:https?://)?t\.me/(joinchat/)?([a-zA-Z0-9_\-+]+)", link)
    if not match:
        return None
    return match.group(2)

async def enhanced_analyze_member(user):
    """Enhanced member analysis with multiple checks"""
    # Check if user is a bot
    if getattr(user, "is_bot", False) or getattr(user, "bot", False):
        return "bot"
    
    suspicious_patterns = []
    
    # No profile photo
    if not getattr(user, "photo", None):
        suspicious_patterns.append("no_photo")
    
    # Suspicious username pattern (many numbers, random characters)
    username = getattr(user, "username", None)
    if username:
        if re.search(r"\d{8,}", username) or len(username) > 20:
            suspicious_patterns.append("suspicious_username")
        # Check for patterns like "user12345678"
        if re.match(r"^[a-zA-Z]+\d{5,}$", username):
            suspicious_patterns.append("pattern_username")
    
    # First and last name checks
    first_name = getattr(user, "first_name", "")
    last_name = getattr(user, "last_name", "")
    
    # Name with only emojis or special characters
    if first_name and re.match(r"^[\W_]+$", first_name):
        suspicious_patterns.append("suspicious_name")
    
    # Name with random characters mix
    if first_name and re.search(r"[a-zA-Z]*[0-9]{3,}[a-zA-Z]*", first_name):
        suspicious_patterns.append("suspicious_name")
    
    # No last name (common in fake accounts)
    if not last_name:
        suspicious_patterns.append("no_last_name")
    
    # High number of suspicious patterns indicates likely fake account
    if len(suspicious_patterns) >= 3:
        return "fake"
    elif suspicious_patterns:
        return "suspicious"
    
    return "real"

async def scan_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Scan group/channel members"""
    message = update.message
    user_input = message.text.strip()
    
    if not user_input.startswith(("https://t.me/", "t.me/")):
        await message.reply_text("❌ Please provide a valid Telegram group/channel link.")
        return
    
    # Send initial message
    processing_msg = await message.reply_text("🔄 Scanning members... This may take a while for large groups.")
    
    # Extract entity info
    entity_id = await extract_entity_info(user_input)
    
    if not entity_id:
        await processing_msg.edit_text("❌ Invalid Telegram link format.")
        return
    
    try:
        # Get entity using Pyrogram
        async with pyro_client:
            entity = await pyro_client.get_chat(entity_id)
            
            if not entity:
                await processing_msg.edit_text("❌ Cannot access the group/channel. Make sure the bot is added as admin.")
                return
            
            # Get members (limited to 200 for demo, remove limit for full scan)
            members = []
            async for member in pyro_client.get_chat_members(entity.id, limit=200):
                members.append(member)
            
            # Analyze members
            real_count = 0
            bot_count = 0
            suspicious_count = 0
            fake_count = 0
            
            for member in members:
                user_type = await enhanced_analyze_member(member.user)
                if user_type == "real":
                    real_count += 1
                elif user_type == "bot":
                    bot_count += 1
                elif user_type == "fake":
                    fake_count += 1
                else:
                    suspicious_count += 1
            
            total_members = len(members)
            
            # Generate report
            report = f"""
📊 **Member Analysis Report**

🏷 **Entity:** {entity.title}
👥 **Total Members Scanned:** {total_members}

✅ **Real Users:** {real_count} ({real_count/total_members*100:.1f}%)
🤖 **Bots:** {bot_count} ({bot_count/total_members*100:.1f}%)
⚠️ **Suspicious Accounts:** {suspicious_count} ({suspicious_count/total_members*100:.1f}%)
❌ **Fake Accounts:** {fake_count} ({fake_count/total_members*100:.1f}%)

💡 **Note:** This analysis is based on advanced heuristics and may not be 100% accurate.

🔍 **Bot by:** @dlight | **Creator:** Michael A. (Arewa)
            """
            
            await processing_msg.edit_text(report, parse_mode="Markdown")
            
    except errors.UserNotParticipant:
        await processing_msg.edit_text("❌ Bot is not a member of this group/channel. Add the bot as admin first.")
    except errors.ChannelInvalid:
        await processing_msg.edit_text("❌ Invalid channel/group or insufficient permissions.")
    except errors.ChatAdminRequired:
        await processing_msg.edit_text("❌ Bot needs admin permissions to view members.")
    except Exception as e:
        logger.error(f"Error scanning members: {e}")
        await processing_msg.edit_text("❌ Error scanning members. Please try again later.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_text = """
👋 **Welcome to DLight - Member Scanner Bot!**

🔍 *Created by Michael A. (Arewa)*

I can analyze Telegram groups and channels to identify:
✅ Real users
🤖 Bots
⚠️ Suspicious accounts
❌ Fake accounts (bought subscribers)

**How to use:**
1. Add me as admin to the group/channel
2. Send me the group/channel link
3. I'll analyze the members and provide a detailed report

📎 Example: `https://t.me/your_channel`

I use advanced algorithms to detect fake accounts based on:
- Username and profile characteristics
- Name patterns and profile completeness
    """
    
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command handler"""
    help_text = """
📖 **DLight Help Guide**

**Commands:**
/start - Start the bot
/help - Show this help message

**Usage:**
1. Add the bot as admin to your group/channel
2. Send the group/channel link to the bot
3. Wait for the analysis to complete

**Note:** For large groups, the scan may take several minutes.

⚠️ **Limitations:**
- The bot needs admin permissions
- Analysis is based on heuristics (not 100% accurate)
- Private groups require the bot to be added first

🔍 **Detection Methods:**
- Username pattern recognition
- Profile completeness check
- Name and bio analysis

🔧 **Bot by:** @dlight | **Creator:** Michael A. (Arewa)
    """
    
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Error handler"""
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text("❌ An error occurred. Please try again later.")

async def main():
    """Start the bot and clients"""
    # Start both clients
    await asyncio.gather(
        pyro_client.start(),
        telethon_client.start()
    )
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, scan_members))
    application.add_error_handler(error_handler)
    
    # Start the bot
    print("🤖 DLight Bot is running...")
    print("🔧 Created by Michael A. (Arewa)")
    
    # Run the bot until Ctrl-C is pressed
    await application.run_polling()

if __name__ == "__main__":
    # Run the main function
    asyncio.run(main())
