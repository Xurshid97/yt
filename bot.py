import os
import yt_dlp
import logging
import asyncio
import multiprocessing
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext
from telethon.sync import TelegramClient
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# Set up logging
logging.basicConfig(level=logging.INFO)

load_dotenv()

# Environment variables
BOT_TOKENS = os.getenv("BOT_TOKENS").split(",")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")
PRIVATE_GROUP_ID = int(os.getenv("PRIVATE_GROUP_ID"))
GOOGLE_EMAIL = os.getenv("GOOGLE_EMAIL")  # Renamed for clarity
GOOGLE_PASSWORD = os.getenv("GOOGLE_PASSWORD")

# Initialize Telegram Client (Uploader)
uploader_client = TelegramClient("uploader", API_ID, API_HASH)

# Dictionary to track user requests
user_requests = {}
COOKIES_FILE = "/app/cookies.txt"
CONTEXT_DIR = "/app/browser_context"  # Directory to store persistent browser state

async def initialize_browser_context():
    """Log into Google and save the browser context for reuse."""
    try:
        async with async_playwright() as p:
            # Create a persistent context (saves cookies, local storage, etc.)
            context = await p.chromium.launch_persistent_context(
                CONTEXT_DIR,
                headless=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            # If context is new (no cookies), log in
            cookies = await context.cookies("https://accounts.google.com")
            if not cookies:
                await page.goto("https://accounts.google.com/ServiceLogin")
                await page.fill("input[type='email']", GOOGLE_EMAIL)
                await page.click("#identifierNext", timeout=60000)
                await page.wait_for_timeout(2000)

                # Password step with retry logic
                for attempt in range(3):
                    try:
                        await page.fill("input[type='password']", GOOGLE_PASSWORD)
                        await page.click("#passwordNext", timeout=60000)
                        await page.wait_for_timeout(5000)
                        break
                    except Exception as e:
                        logging.warning(f"Login attempt {attempt + 1} failed: {e}")
                        if attempt == 2:
                            raise Exception("Failed to log in after retries")
                        await page.wait_for_timeout(2000)

                # Verify login by visiting Google
                await page.goto("https://www.google.com")
                await page.wait_for_load_state("networkidle", timeout=60000)

                # Save the context (cookies are stored in CONTEXT_DIR)
                await context.close()
                logging.info("Initialized browser context with Google login.")
            else:
                logging.info("Reusing existing browser context.")
                await context.close()

    except Exception as e:
        logging.error(f"Error initializing browser context: {e}")
        raise

async def generate_youtube_cookies():
    """Generate YouTube cookies using the authenticated browser context."""
    try:
        async with async_playwright() as p:
            # Reuse the persistent context
            context = await p.chromium.launch_persistent_context(
                CONTEXT_DIR,
                headless=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()
            await page.goto("https://www.youtube.com", timeout=60000)

            # Wait for YouTube to load
            await page.wait_for_load_state("networkidle", timeout=60000)

            # Export cookies
            cookies = await context.cookies("https://www.youtube.com")
            await context.close()

            with open(COOKIES_FILE, "w") as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write(f"# Generated on {subprocess.getoutput('date')}\n")
                for cookie in cookies:
                    f.write(f"{cookie['domain']}\tTRUE\t{cookie['path']}\t{'TRUE' if cookie['secure'] else 'FALSE'}\t"
                            f"{int(cookie['expires']) if cookie['expires'] else 0}\t{cookie['name']}\t{cookie['value']}\n")
            
            logging.info("Generated YouTube cookies from authenticated browser context.")
            return os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 50

    except Exception as e:
        logging.error(f"Error generating cookies: {e}")
        return False

async def ensure_cookies():
    """Ensure cookies are available and valid; regenerate if needed."""
    if not os.path.exists(COOKIES_FILE) or os.path.getsize(COOKIES_FILE) <= 50:
        return await generate_youtube_cookies()
    return True

async def get_available_formats(url):
    """Fetch available video formats with cookies."""
    has_cookies = await ensure_cookies()
    if not has_cookies:
        return {}

    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
        'geo_bypass': True,
        'http_headers': {'User-Agent': 'Mozilla/5.0'},
        'cookiefile': COOKIES_FILE,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.get_event_loop().run_in_executor(None, ydl.extract_info, url, False)
            formats = info.get("formats", [])
            available_formats = {str(fmt["height"]): fmt["format_id"] for fmt in formats if fmt.get("vcodec") != "none" and fmt.get("height")}
            return available_formats
    except Exception as e:
        logging.error(f"Error fetching formats: {e}")
        return {}

async def download_video(url):
    """Download video with best audio merged using cookies."""
    await ensure_cookies()
    ydl_opts = {
        'format': 'bv*+ba/b',
        'outtmpl': '/app/downloads/%(title)s.%(ext)s',
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'cookiefile': COOKIES_FILE,
    }

    loop = asyncio.get_event_loop()
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = await loop.run_in_executor(None, ydl.extract_info, url, True)
        video_path = ydl.prepare_filename(info_dict)
    
    return video_path

def get_file_size(file_path):
    """Get video file size in MB."""
    return os.path.getsize(file_path) / (1024 * 1024)

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text("Send me a video link from YouTube, Instagram, or other social media platforms.")

async def handle_message(update: Update, context: CallbackContext):
    url = update.message.text.strip()
    user_id = update.message.from_user.id

    if any(site in url for site in ["youtube.com", "youtu.be", "instagram.com", "tiktok.com", "facebook.com", "twitter.com"]):
        user_requests[user_id] = url
        available_formats = await get_available_formats(url)

        if not available_formats:
            has_cookies = await ensure_cookies()
            if "youtube" in url and not has_cookies:
                await update.message.reply_text("No video formats available. YouTube cookies may be missing or invalid.")
            else:
                await update.message.reply_text("No video formats available. Try another link.")
            return

        keyboard = [[InlineKeyboardButton(f"{q}p", callback_data=q)] for q in sorted(available_formats.keys(), key=int)]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text("Choose available video quality:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Please send a valid video link.")

async def handle_quality_selection(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    quality = query.data
    user_id = query.from_user.id
    url = user_requests.get(user_id)

    if not url:
        await query.message.reply_text("Error: No URL found. Please send the video link again.")
        return

    await query.edit_message_text(f"Downloading video in {quality}p... Please wait.")
    asyncio.create_task(process_video_download_and_upload(url, user_id, context))

async def process_video_download_and_upload(url, user_id, context):
    try:
        video_path = await download_video(url)
        file_size = get_file_size(video_path)

        if file_size <= 50:
            await context.bot.send_video(chat_id=user_id, video=open(video_path, "rb"))
        else:
            await context.bot.send_message(chat_id=user_id, text=f"Video is {file_size:.2f}MB. Uploading via bot...")
            await upload_and_forward_video(video_path, user_id, context)

        if os.path.exists(video_path):
            os.remove(video_path)
            logging.info(f"Deleted video file: {video_path}")

    except Exception as e:
        logging.error(f"Error processing video: {e}")
        await context.bot.send_message(chat_id=user_id, text="An error occurred while processing your video.")

async def upload_and_forward_video(video_path, user_id, context):
    try:
        async with uploader_client:
            await uploader_client.connect()
            group_entity = await uploader_client.get_entity(PRIVATE_GROUP_ID)

            sent_message = await uploader_client.send_file(group_entity, video_path)
            uploaded_message_id = sent_message.id

            if uploaded_message_id:
                await context.bot.forward_message(
                    chat_id=user_id,
                    from_chat_id=PRIVATE_GROUP_ID,
                    message_id=uploaded_message_id
                )
                await context.bot.send_message(chat_id=user_id, text="Upload completed and sent to you.")
            else:
                await context.bot.send_message(chat_id=user_id, text="Failed to retrieve uploaded video.")

    except Exception as e:
        logging.error(f"Error uploading video: {e}")
        await context.bot.send_message(chat_id=user_id, text="An error occurred while uploading your video.")

def start_bot(token):
    app = Application.builder().token(token).read_timeout(600).write_timeout(600).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_quality_selection))

    logging.info(f"Starting bot with token: {token[:6]}...")
    app.run_polling()

async def refresh_cookies_periodically():
    while True:
        await generate_youtube_cookies()
        await asyncio.sleep(24 * 60 * 60)  # Refresh every 24 hours

def main():
    # Ensure the context directory exists
    os.makedirs(CONTEXT_DIR, exist_ok=True)

    # Initialize browser context with login (run once)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(initialize_browser_context())

    # Generate initial cookies
    loop.run_until_complete(ensure_cookies())

    # Start the cookie refresh task
    loop.create_task(refresh_cookies_periodically())

    # Start bot processes
    processes = []
    for token in BOT_TOKENS:
        p = multiprocessing.Process(target=start_bot, args=(token,))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()

if __name__ == "__main__":
    main()