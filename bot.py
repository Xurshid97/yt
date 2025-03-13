
import os
import yt_dlp
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, CallbackContext
from telethon.sync import TelegramClient
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)

load_dotenv()

# Retrieve credentials from environment variables
TOKEN = os.getenv("TOKEN")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")
PRIVATE_GROUP_ID = int(os.getenv("PRIVATE_GROUP_ID"))

# Initialize Telegram Client (Uploader)
uploader_client = TelegramClient("uploader", API_ID, API_HASH)

# Dictionary to track user requests (user_id → YouTube URL)
user_requests = {}

def get_available_formats(url):
    """Fetch available video formats for the given YouTube URL."""
    ydl_opts = {
        'quiet': True,
        'noplaylist': True,
        'geo_bypass': True,
        'extractor_args': {'youtube': {'player_client': ['android']}},
        'http_headers': {'User-Agent': 'Mozilla/5.0'},
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

async def download_youtube_video(url, quality):
    """Download YouTube video in the selected quality asynchronously."""
    available_formats = get_available_formats(url)
    format_id = available_formats.get(quality) or max(available_formats.keys(), key=int)

    ydl_opts = {
        'format': format_id,
        'outtmpl': 'downloads/%(title)s.%(ext)s',
        'merge_output_format': 'mp4',
        'noplaylist': True,
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
    await update.message.reply_text("Send me a YouTube link and choose a quality.")

async def handle_message(update: Update, context: CallbackContext):
    url = update.message.text.strip()
    user_id = update.message.from_user.id

    if "youtube.com" in url or "youtu.be" in url:
        user_requests[user_id] = url
        available_formats = get_available_formats(url)

        if not available_formats:
            await update.message.reply_text("No video formats available. Try another link.")
            return

        keyboard = [[InlineKeyboardButton(f"{q}p", callback_data=q)] for q in sorted(available_formats.keys(), key=int)]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text("Choose available video quality:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Please send a valid YouTube link.")

async def handle_quality_selection(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    quality = query.data
    user_id = query.from_user.id
    url = user_requests.get(user_id)

    if not url:
        await query.message.reply_text("Error: No URL found. Please send the YouTube link again.")
        return

    await query.edit_message_text(f"Downloading video in {quality}p... Please wait.")

    # Run the download and upload in the background
    asyncio.create_task(process_video_download_and_upload(url, quality, user_id, context))

async def process_video_download_and_upload(url, quality, user_id, context):
    """Handles downloading and uploading the video in parallel."""
    try:
        video_path = await download_youtube_video(url, quality)
        file_size = get_file_size(video_path)

        if file_size <= 50:
            await context.bot.send_video(chat_id=user_id, video=open(video_path, "rb"))
        else:
            await context.bot.send_message(chat_id=user_id, text=f"Video is {file_size:.2f}MB. Uploading via bot...")

            # Run the upload in the background
            asyncio.create_task(upload_and_forward_video(video_path, user_id, context))

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

def main():
    app = Application.builder().token(TOKEN).read_timeout(600).write_timeout(600).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_quality_selection))

    uploader_client.start(PHONE_NUMBER)
    app.run_polling()

if __name__ == "__main__":
    main()

