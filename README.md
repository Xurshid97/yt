# YouTube Video Downloader Telegram Bot

This bot allows users to download YouTube videos in various qualities and receive them directly on Telegram. If the file is too large, it is uploaded to a private group and forwarded to the user.

## Features

- Fetch available video formats.
- Download videos in the selected quality.
- Upload large files to a private group and forward them.
- Works asynchronously to handle multiple users without blocking.

## Installation

### 1. Clone the Repository

```sh
git clone https://github.com/Xurshid97/yt.git
cd yt
```

### 2. Set Up a Virtual Environment

```sh
python -m venv venv
source venv/bin/activate  # On macOS/Linux
venv\Scripts\activate    # On Windows
```

### 3. Install Dependencies

```sh
pip install -r requirements.txt
```

### 4. Set Up Environment Variables

Create a `.env` file in the root directory and add your credentials:

```ini
TOKEN=<your-telegram-bot-token>
API_ID=<your-telegram-api-id>
API_HASH=<your-telegram-api-hash>
PHONE_NUMBER=<your-telegram-phone-number>
PRIVATE_GROUP_ID=<your-private-group-id>
```

## Running the Bot

```sh
python bot.py
```

## Running the Bot Non-Stop on a Server

To keep the bot running continuously on a server, use `systemd` for better reliability.

### Using `systemd` (Recommended)

1. Create a systemd service file:

```sh
sudo nano /etc/systemd/system/youtube_bot.service
```

2. Add the following content (update the paths accordingly):

```ini
[Unit]
Description=YouTube Video Downloader Telegram Bot
After=network.target

[Service]
ExecStart=/path/to/venv/bin/python /path/to/repository/bot.py
WorkingDirectory=/path/to/repository
Environment="TOKEN=<your-telegram-bot-token>"
Environment="API_ID=<your-telegram-api-id>"
Environment="API_HASH=<your-telegram-api-hash>"
Environment="PHONE_NUMBER=<your-telegram-phone-number>"
Environment="PRIVATE_GROUP_ID=<your-private-group-id>"
Restart=always
User=<your-server-username>

[Install]
WantedBy=multi-user.target
```

3. Reload systemd and enable the service:

```sh
sudo systemctl daemon-reload
sudo systemctl enable youtube_bot
sudo systemctl start youtube_bot
```

4. Check bot status:

```sh
sudo systemctl status youtube_bot
```

5. To view logs:

```sh
journalctl -u youtube_bot -f
```

## Logging

The bot uses Python’s built-in `logging` module. Logs can be found in the console output or redirected to a file if needed.

## Contributing

Feel free to submit issues and pull requests to improve the bot!

## License

MIT License

