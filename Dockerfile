FROM python:3.10-slim

# Prevent interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:99

# Install system dependencies, XVFB, VNC, noVNC, and supervisor
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    supervisor \
    libxi6 \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome stable via direct deb package (bypasses deprecated apt-key)
RUN wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependencies list and install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and supervisord config
COPY . .

# Create required directories
RUN mkdir -p /app/chrome_profile /app/output_images /app/temp_downloads /var/log/supervisor

# Expose FastAPI Web App (8000) and noVNC Live Stream (6080)
EXPOSE 8000 6080

# Launch supervisord to manage display server, VNC stream, and web dashboard
CMD ["/usr/bin/supervisord", "-c", "/app/supervisord.conf"]
