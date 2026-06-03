# nas-md

Private, quiet space for thinking. A simple app for your `.md` files.

A personal knowledge management system — notes, journal, habits, checklists, and more. All in plain `.md` files, local-first. LLM-friendly. **Private - your data stays on your device.**

> Own your data as plain local files.
> Own the software that opens those files.
> Grow your knowledge with files and your own brain.
> **Plain files and self-owned software can last through the ages**.

## Features

- **Notes** — plain Markdown files, one idea per note
- **Journal** — daily records in `journal/YYYY.MM Month.md`
- **Habits** — track daily habits with heatmap visualization
- **Checklists** — `Read.md`, `Watch.md`, `Shop.md`, etc.
- **Tasks** — quick capture with `Later.md`
- **Telegram Bot** — on-the-go access to your files
- **PWA Frontend** — works offline, installable in browser
- **Mount Points** — browse any directory on the server (read-write)
- **Docker Support** — deploy with Docker Compose
- **Cross-Platform** — Windows, Linux, macOS

## Quick Start

### Option 1: One-Click Start (No Docker)

Requires **Python 3.11+**. No other dependencies — the project uses only the Python standard library.

```bash
# Clone the repository
git clone https://github.com/Qboy-1214/nas-md.git
cd nas-md

# Start the server
python3 start.py
```

The server will be available at `http://127.0.0.1:8080`. A browser window will open automatically.

#### Custom Configuration

```bash
# Custom port
WEB_PORT=9000 python3 start.py

# Mount additional directories (semicolon-separated)
WEB_PORT=9000 MOUNT_DIRS="/home/user/notes;/home/user/docs" python3 start.py

# Windows
set WEB_PORT=9000 && python start.py
```

#### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_PORT` | `8080` | HTTP server port |
| `WEB_HOST` | `127.0.0.1` | HTTP server bind address |
| `WEB_ROOT` | `./web` | PWA frontend directory |
| `STORAGE_DIR` | `./storage` | File storage directory |
| `TOKENS_DIR` | `./tokens` | Auth tokens directory |
| `MOUNT_DIRS` | *(empty)* | Semicolon-separated list of absolute paths to serve as browseable mount points |
| `BOT_API_TOKEN` | *(empty)* | Telegram Bot API token (optional) |
| `APP_URL` | *(empty)* | Public URL of the web app |
| `API_URL` | *(empty)* | Public URL of the sync API |

### Option 2: Docker Compose

Requires [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/).

```bash
# Start the server
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

The server will be available at `http://localhost`. Data is persisted in Docker named volumes (`storage` and `tokens`).

#### Docker Compose with Mount Points

Edit `compose.yaml` to mount additional host directories:

```yaml
services:
  nas-md:
    # ... existing config ...
    volumes:
      - storage:/app/storage
      - tokens:/app/tokens
      - /path/to/notes:/mnt/notes     # Mount host directory
      - /path/to/docs:/mnt/docs       # Mount host directory
    environment:
      # ... existing env vars ...
      MOUNT_DIRS: /mnt/notes;/mnt/docs
```

Then start:

```bash
docker compose up -d
```

#### Manual Docker Build & Run

```bash
# Build the image
docker build -t nas-md .

# Run the container
docker run --rm -it -p 80:8080 \
  -v nas-md-storage:/app/storage \
  -v nas-md-tokens:/app/tokens \
  -e APP_URL=http://localhost \
  nas-md
```

## Mount Points (Browse Server Directories)

Mount points allow you to browse directories on the server through the web UI. Each mounted directory appears as a separate entry in the sidebar selector.

**Features:**
- Browse nested directory trees
- View and edit Markdown files
- Preview media files (images, audio, video)
- Create, rename, and delete files and directories
- Path traversal protection (cannot escape mount root)

**API Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/mounts` | List all mount points |
| `GET` | `/api/mounts/{id}/tree?path=/` | List directory contents |
| `GET` | `/api/mounts/{id}/tree-recursive?path=/` | Recursive directory tree (up to 10 levels) |
| `GET` | `/api/mounts/{id}/file?path=/file.md` | Download/read a file |
| `PUT` | `/api/mounts/{id}/file?path=/file.md` | Write/create a file |
| `PUT` | `/api/mounts/{id}/rename?oldPath=/a.md&newPath=/b.md` | Rename/move a file or directory |
| `PUT` | `/api/mounts/{id}/mkdir?path=/newdir` | Create a directory |
| `DELETE` | `/api/mounts/{id}/file?path=/file.md` | Delete a file or directory |

## Files Structure

You don't have to think about the structure — it is predefined. Although, you're free to use whatever structure you want.

- Chat: `Chat.md`
- Notes: `brain/Note.md`, `<category>/*.md`
- Projects: `Project.md`, `*.md`
- Checklists: `Read.md`, `Watch.md`, `Shop.md`
- Journal: `journal/2024.08 August.md`
- Tasks: `Later.md`
- Habits: `habits/Ate consciously.md`, `habits/*.md`
- Images: `media/*` (png, jpg, webp, gif)
- Archive: `archive/*.md`
- Config: `config.json`

## Hotkeys

| Hotkey | Action |
|--------|--------|
| `[` | Insert a link to a file |
| `Cmd+K` / `Ctrl+K` | Open file search modal |
| `Cmd+N` / `Ctrl+N` | New file |
| `Cmd+M` / `Ctrl+M` | Move file |
| `Cmd+D` / `Ctrl+D` | Delete file |
| `Cmd+Enter` / `Ctrl+Enter` | Open chat |
| `Cmd+Shift+Enter` / `Ctrl+Shift+Enter` | Toggle chat dialog |
| `Cmd+[` / `Ctrl+[` | Go to previous file |
| `Cmd+]` / `Ctrl+]` | Go to next file |
| `Cmd+~` / `Ctrl+~` | Toggle sidebar |
| `T` | Toggle theme (auto/light/dark) |
| `L` | Toggle layout (auto/landscape/portrait) |
| `Cmd+B` / `Ctrl+B` | Toggle **bold** |
| `Cmd+I` / `Ctrl+I` | Toggle *italic* |
| `Cmd+Y` / `Ctrl+Y` | Insert checkbox |
| `Cmd/Ctrl` + `Click` | Copy inline text / open link |

## Documentation

- [Deploy on your own server](docs/your-own-server.md)
- [Mount API Reference](docs/mount-api.md)

## Repository Structure

```
nas-md/
├── start.py              # One-click launcher (cross-platform)
├── compose.yaml          # Docker Compose configuration
├── Dockerfile            # Docker image definition
├── pyproject.toml        # Python project config (black, ruff, pytest)
├── nas_md/               # Python package
│   ├── cli/              # CLI entry points
│   │   ├── __init__.py   # Command implementations
│   │   └── __main__.py   # python3 -m nas_md.cli support
│   ├── config/           # Configuration (env vars)
│   ├── webserver/        # HTTP server + mount API
│   ├── server/           # Telegram bot server
│   ├── sync/             # Sync API
│   ├── fs/               # File system utilities
│   ├── db/               # Database (SQLite)
│   ├── habits/           # Habit tracking
│   ├── journal/          # Journal management
│   ├── stats/            # Statistics
│   ├── worker/           # Scheduled tasks
│   ├── plugins/          # Plugin system
│   ├── i18n/             # Internationalization
│   ├── userconfig/       # User configuration
│   └── pkg/              # Shared packages
│       └── txt/          # Text processing (hash, timestamps, etc.)
├── web/                  # PWA frontend
│   ├── index.html        # Entry point
│   ├── app.js            # Main app logic
│   ├── files.js          # File browser
│   ├── mount-manager.js  # Mount point UI
│   ├── editor.js         # Markdown editor
│   ├── chat.js           # Chat interface
│   ├── layout.css        # Layout styles
│   ├── app.css           # App styles
│   └── lib/              # Frontend libraries
├── tests/                # Test suite (272 tests)
└── docs/                 # Documentation
```

## Running Tests

```bash
# Run all tests
PYTHONPATH=. python3 -m pytest tests/ -v

# Run with coverage
PYTHONPATH=. python3 -m pytest tests/ -v --cov=nas_md --cov-report=term-missing
```

## Backend Guidelines

- We write **tests**
- No panics, errors are part of business logic
- If we are ignoring an error — we leave a WHY comment
- We wrap errors all the time, adding method's context
- We prefer real implementations or at least fakes over mocks and stubs
- **With portability in mind, everything is stored in plain `.md` files**
- The codebase is designed to be LLM-friendly — one person or an LLM can fit the whole project in head

## Frontend Guidelines

- No build systems — in 10 years we will open `/web/index.html` and it should just work
- All frontend libraries are vendored in `web/lib/`
- Avoid flaky tests — race conditions are the most common source of bugs

## License

See [LICENSE](LICENSE) for details.
