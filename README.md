Dlight - Telegram Member Scanner Bot
Dlight is a Telegram bot that analyzes public groups or channels to provide an estimated breakdown of active members, inactive members, and bots. It also uses Google's Gemini AI to determine the industry or category of the channel based on its title and description.

This bot was created by Micheal A.

Features
Member Analysis: Scans a channel/group and categorizes members into Active, Inactive, and Bots based on their last seen status.

Industry Detection: Utilizes the Gemini API to analyze the channel's purpose.

Secure: Uses environment variables to protect sensitive API keys and session data, making it safe for cloud deployment.

Easy Deployment: Designed to be easily deployed on cloud platforms like Render.

Setup and Deployment Guide
Follow these steps carefully to get your bot running. You will need to run a script locally once before deploying.

Step 1: Get Telegram API Credentials
Before you can use the Telegram API, you need your own API_ID and API_HASH.

Go to my.telegram.org and log in with your Telegram account.

Click on API development tools.

Fill in the "App title" and "Short name" (you can call it "Dlight Bot" or anything else).

You will be given your api_id and api_hash. Keep these secret and save them for later.

Step 2: Create a Telegram Bot
Open Telegram and search for the @BotFather user.

Start a chat and send the /newbot command.

Follow the instructions to choose a name (e.g., "Dlight Scanner") and a username (e.g., DlightScannerBot).

BotFather will give you a token. This is your BOT_TOKEN. Keep it secret and save it.

Step 3 (Optional but Recommended): Get a Gemini API Key
For the industry analysis feature, you need a Gemini API key.

Go to Google AI Studio.

Click on "Create API key in new project".

Copy the generated API key. This is your GEMINI_API_KEY. Save it for later.

Step 4: Prepare Your Project on GitHub
Make sure you have all the project files (bot.py, generate_session.py, requirements.txt) in a folder on your computer.

Create a new repository on GitHub.

Upload the project files to this new repository.

Step 5: Generate Your TELETHON_SESSION (Crucial Step)
You must do this on your local computer before deploying.

Make sure you have Python installed on your computer.

Open your terminal or command prompt.

Navigate to your project folder.

Install the required libraries locally by running:

pip install -r requirements.txt

Now, run the session generator script:

python generate_session.py

The script will ask you for your API_ID, API_HASH, phone number, login code (sent to your Telegram), and password (if you have 2FA).

After a successful login, it will print a very long string of text. This is your TELETHON_SESSION.

Copy this entire string and save it. You will need it for the final deployment step.

Step 6: Deploy on Render
Go to Render.com and create an account.

On your dashboard, click New + and select Web Service.

Connect your GitHub account and select the repository for your bot.

Configure the service with the following settings:

Name: Give your bot a name (e.g., dlight-bot).

Region: Choose a region close to you.

Branch: main (or your default branch).

Build Command: pip install -r requirements.txt

Start Command: python bot.py

Click on Advanced or scroll down to the Environment Variables section. Add the following key-value pairs:

API_ID: Your API ID from Step 1.

API_HASH: Your API Hash from Step 1.

BOT_TOKEN: Your Bot Token from Step 2.

TELETHON_SESSION: The long session string you generated in Step 5.

GEMINI_API_KEY: The Gemini key from Step 3 (if you got one).

PYTHON_VERSION: 3.10 (or a recent version).

Click Create Web Service. Render will now build and deploy your bot. You can watch the progress in the logs.

Once deployed, your bot will be live! You can now interact with it on Telegram.
