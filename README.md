# YouTube Video Downloader Telegram Bot

This is a Telegram bot that allows users to download YouTube videos by sending a link. Users can select the video quality before downloading. If the video is too large, it is uploaded to a private Telegram group and forwarded to the user.

## Features
- Download YouTube videos in various qualities.
- Upload large videos to a private Telegram group.
- Forward uploaded videos to users.
- Asynchronous processing for better performance.

## Installation

### 1. Clone the repository
```sh
git clone https://github.com/Xurshid97/yt.git
cd yt
```

### 2. Create and activate a virtual environment

#### On Windows:
```sh
python -m venv venv
venv\Scripts\activate
```

#### On macOS/Linux:
```sh
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies
```sh
pip install -r requirements.txt
```

## Configuration

### 1. Create a `.env` file in the project directory and add the following variables:
```
TOKEN=your-telegram-bot-token
API_ID=your-telegram-api-id
API_HASH=your-telegram-api-hash
PHONE_NUMBER=your-telegram-phone-number
PRIVATE_GROUP_ID=your-private-group-id
```

### 2. Run the bot
```sh
python bot.py
```

## Usage
1. Start the bot by sending `/start`.
2. Send a YouTube link.
3. Select the desired video quality.
4. Wait for the bot to process and send the video.

## Dependencies
- `python-telegram-bot`
- `telethon`
- `yt-dlp`
- `python-dotenv`

## License
This project is licensed under the MIT License.

