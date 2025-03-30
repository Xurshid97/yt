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

# Set up logging
logging.basicConfig(level=logging.INFO)

load_dotenv()

# Store multiple bot tokens (Comma-separated in .env)
BOT_TOKENS = os.getenv("BOT_TOKENS").split(",")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")
PRIVATE_GROUP_ID = int(os.getenv("PRIVATE_GROUP_ID"))

# Initialize Telegram Client (Uploader)
uploader_client = TelegramClient("uploader", API_ID, API_HASH)

# Dictionary to track user requests (user_id → Video URL)
user_requests = {}

# Path to Firefox profile and cookies file
FIREFOX_PROFILE = os.path.expanduser("~/snap/firefox/common/.mozilla/firefox/cp4r6cfh.default")
COOKIES_FILE = "cookies.txt"

def ensure_cookies():
    """Fallback: Generate cookies.txt from Firefox profile if needed."""
    if not os.path.exists(COOKIES_FILE):
        result = subprocess.run([
            "sqlite3", f"{FIREFOX_PROFILE}/cookies.sqlite",
            "SELECT host, name, value FROM moz_cookies WHERE host LIKE '%youtube%';"
        ], capture_output=True, text=True)
        with open("youtube_cookies.txt", "w") as f:
            f.write(result.stdout)
        with open("youtube_cookies.txt", "r") as f, open(COOKIES_FILE, "w") as out:
            out.write("# Netscape HTTP Cookie File\n")
            out.write(f"# Generated on {subprocess.getoutput('date')}\n")
            for line in f:
                if line.strip():
                    host, name, value = line.strip().split("|")
                    out.write(f"{host}\tTRUE\t/\tTRUE\t0\t{name}\t{value}\n")
        os.remove("youtube_cookies.txt")
        logging.info("Generated cookies.txt from Firefox profile.")
    return os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 50

def get_available_formats(url):
    """Fetch available video formats with cookies."""
    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
        'geo_bypass': True,
        'http_headers': {'User-Agent': 'Mozilla/5.0'},
        'cookiesfrombrowser': ('firefox', FIREFOX_PROFILE),  # Use cookies directly from Firefox profile
        # 'cookiefile': COOKIES_FILE,  # Fallback: Uncomment if --cookies-from-browser fails
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get("formats", [])
            available_formats = {str(fmt["height"]): fmt["format_id"] for fmt in formats if fmt.get("vcodec") != "none" and fmt.get("height")}
            return available_formats
    except Exception as e:
        logging.error(f"Error fetching formats: {e}")
        return {}

async def download_video(url):
    """Download video with best audio merged using cookies."""
    ydl_opts = {
        'format': 'bv*+ba/b',
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'cookiesfrombrowser': ('firefox', FIREFOX_PROFILE),  # Use cookies directly from Firefox profile
        # 'cookiefile': COOKIES_FILE,  # Fallback: Uncomment if --cookies-from-browser fails
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
        available_formats = get_available_formats(url)

        if not available_formats:
            has_cookies = ensure_cookies()
            if "youtube" in url and not has_cookies:
                await update.message.reply_text("No video formats available. YouTube login cookies may be missing or expired.")
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
    """Handles downloading and uploading the video in parallel."""
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
    """Uploads video to private group and forwards it to the user."""
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
    """Initialize and run a bot instance."""
    app = Application.builder().token(token).read_timeout(600).write_timeout(600).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_quality_selection))

    logging.info(f"Starting bot with token: {token[:6]}...")
    app.run_polling()

def main():
    os.makedirs("downloads", exist_ok=True)
    # ensure_cookies()  # Uncomment if using --cookiefile fallback

    processes = []
    for token in BOT_TOKENS:
        p = multiprocessing.Process(target=start_bot, args=(token,))
        p.start()
        processes.append(p)

    for p in processes:
        p.join()

if __name__ == "__main__":
    main()