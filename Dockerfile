# Use an official Python runtime as the base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for Playwright, yt-dlp, ffmpeg, and Telegram bot
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libx11-xcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxi6 \
    libxtst6 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and its browser binaries
RUN pip install playwright && playwright install chromium

# Copy the application code
COPY . .

# Ensure downloads directory exists
RUN mkdir -p downloads

# Set environment variables (optional, can be overridden by docker-compose or .env)
ENV PYTHONUNBUFFERED=1

# Command to run the bot
CMD ["python", "bot.py"]