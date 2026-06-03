# Deploy on Your Own Server

## Quick Start with start.py (Recommended for Testing)

The easiest way to run the server locally:

```bash
python3 start.py
```

This will start the server at `http://127.0.0.1:8080` with sensible defaults. See the main [README](../README.md) for configuration options.

## Containerized Deployment (Docker/Podman)

### Docker Compose (Recommended for Production)

```bash
# Start in foreground
docker compose up

# Start in background
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

The server will be available at `http://localhost`. Data is persisted in Docker named volumes (`storage` and `tokens`).

### Enable HTTPS

In `compose.yaml`: set `CERT_DIR` to a persistent path, uncomment the `"443:443"` port.

### Using Podman

All Docker commands work with Podman as a drop-in replacement:

```bash
# Build
podman build -t nas-md .

# Run
podman run --rm -it -p 80:8080 \
  -v nas-md-storage:/app/storage \
  -e APP_URL=http://localhost \
  nas-md

# Compose
podman-compose up -d
```

## Deploy on Your Own Server (Manual)

### Prerequisites

- **Python 3.11+** (no other dependencies required)
- A Linux server (Debian/Ubuntu recommended)

### Step 1: Clone and Start

```bash
git clone https://github.com/Qboy-1214/nas-md.git
cd nas-md

# Start directly
python3 start.py
```

### Step 2: Configure Environment

Create a `.env` file in the project root:

```env
WEB_PORT=8080
WEB_HOST=0.0.0.0
STORAGE_DIR=/home/user/nas-md-storage
TOKENS_DIR=/home/user/nas-md-tokens
WEB_ROOT=/home/user/nas-md/web
APP_URL=https://yourdomain.com
API_URL=https://api.yourdomain.com
BOT_API_TOKEN=your-telegram-bot-token
MOUNT_DIRS=/mnt/notes;/mnt/docs
```

### Step 3: Run as a Systemd Service (Linux)

Create `/etc/systemd/system/nas-md.service`:

```ini
[Unit]
Description=nas-md personal knowledge management
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/home/your-user/nas-md
Environment=PYTHONPATH=/home/your-user/nas-md
ExecStart=/usr/bin/python3 /home/your-user/nas-md/start.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable nas-md
sudo systemctl start nas-md

# Check status
sudo systemctl status nas-md

# View logs
sudo journalctl -u nas-md -f
```

## Run Your Own Telegram Bot

1. Register a new Telegram bot via [@BotFather](https://t.me/BotFather)
2. Add `BOT_API_TOKEN=<YOUR_TELEGRAM_API_TOKEN>` to your `.env` file
3. Restart the server

Bot artifacts can be seen in `./storage/<USER_ID>` folder.

## Linking a New Device

1. Open the Telegram bot
2. Open `/app`
3. Open the link in your browser
4. Device is now linked

## Hosting the Bot on Your Local Computer

You can host the bot locally. It doesn't expose any ports to the outside world (if you don't use habits functionality). It communicates with Telegram using a polling API.

Create a symlink to your local folder with `.md` files for convenience:

```bash
ln -s <YOUR_EXISTING_DIR_WITH_MD_FILES> storage/<USER_ID>
```

## Transfer Files to Another Server

1. Backup your data (`storage/` directory)
2. Ensure all client apps are fully synced with the server
3. Stop the bot on the old server
4. Compress: `tar -czvf storage.tar.gz storage`
5. Transfer to new server: `scp storage.tar.gz user@newserver:/path/to/nas-md/`
6. Extract on new server: `tar -xzvf storage.tar.gz`
7. Transfer `BOT_API_TOKEN` to the new server's `.env`
8. Launch the server on the new server
9. In your PWA app, update the API host: `localStorage.setItem('ApiHost', 'YOUR_NEW_API_HOST');`

## Maintenance Notes

### Daily Git Backups

Add this to your crontab (`crontab -e`):

```
0 0 * * * cd /app/storage/<YOUR_TELEGRAM_ID> && git add . && git commit -m "$(date +\%d.\%m.\%Y)"
```

Initialize git in your storage folder first:

```bash
cd storage/<YOUR_TELEGRAM_ID>
git init
```

### Non-ASCII Characters in Filenames

If you have non-ASCII characters in filenames, disable quoting:

```bash
git config --global core.quotePath false
```

### Find Forbidden Characters in Filenames

```bash
find . -name '*[<>:\"|\\?*]*'
```

### Remove Forbidden Filename Characters

```bash
find . -type f -name '*[<>:\"|\\?*]*' -print0 | while IFS= read -r -d '' f; do
  dir=$(dirname "$f")
  base=$(basename "$f")
  newbase="${base//[<>:\"|\\\\?*]/}"
  [ "$base" != "$newbase" ] && [ -n "$newbase" ] && mv -n -- "$f" "$dir/$newbase"
done
```
