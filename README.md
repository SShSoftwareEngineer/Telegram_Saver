# Telegram Saver - Content Archive System

Personal archive of Telegram content: select messages in Telegram, save them (with media) to a local database,
then browse, search, tag and export them in a web interface.

## Overview
A single-user application that runs on your computer. It logs in to your Telegram account (Telethon), shows your chats
and messages, and saves the ones you choose to an SQLite database and to a local media directory.

## Features
- **Selective saving**: pick messages from any chat (including "Saved Messages") and save them with their media files
- **Multi-type content**: text, photos, video, audio, documents, link previews, forwarded messages, sender metadata
- **Search and filters**: by chat, date, text and tags (any or all of the tags), both in Telegram and in the archive
- **Tags**: add, remove and rename tags for the checked messages, rename a tag in all messages, sort the tag list,
  pick several tags at once for the tag filter
- **Export**: selected messages to a standalone HTML page with copied media files
- **Maintenance**: report of media files without database records, recreation of lost message HTML files, re-download
  of missing files (up to 100 per run), database backup
- **Database abstraction**: SQLAlchemy ORM with SQLite (the schema is designed to be portable to PostgreSQL)

## Architecture
- **Telegram**: Telethon; its asyncio event loop runs in a background thread
- **Database**: SQLite via SQLAlchemy ORM
- **Web layer**: FastAPI + Jinja2 templates + Vanilla JavaScript; routes return JSON with HTML fragments
- **Concurrency**: regular `def` routes (run by Starlette in a thread pool) and one global lock around the
  application state; the app is single-user and runs with one worker
- **Data flow**: Telegram API → Telethon handler → SQLAlchemy → SQLite → FastAPI routes → browser

## Requirements
- Python 3.14 or newer
- [Poetry](https://python-poetry.org/) for dependency management
- A Telegram account and API credentials (see below)

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/SShSoftwareEngineer/Telegram_Saver.git
   cd Telegram_Saver
   ```
2. **Install Poetry (if not already installed):**
   - Linux/macOS:
     ```bash
     curl -sSL https://install.python-poetry.org | python3 -
     ```
   - Windows (PowerShell):
     ```powershell
     (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -
     ```
3. **Install the dependencies:**
   ```bash
   poetry install
   poetry shell
   ```
4. **Get your Telegram API parameters** (`API_ID` and `API_HASH`):
   1. Open [my.telegram.org](https://my.telegram.org) and log in with your phone number (a code arrives in Telegram).
   2. Open **API development tools**.
   3. Create an application: any *App title* and *Short name*; the platform and description do not matter.
   4. Copy **App api_id** and **App api_hash** from the page. Keep them private: they identify your application and
      belong to your account.
5. **Create the settings file** `configs/.env` (it is excluded from git; `configs/.env.example` is a template):

   | Variable | Description |
   |---|---|
   | `PHONE` | Phone number of the Telegram account in international format, e.g. `+380991234567` |
   | `PASSWORD` | Cloud (two-step verification) password of the account; leave empty if it is not enabled |
   | `API_ID` | `App api_id` from my.telegram.org |
   | `API_HASH` | `App api_hash` from my.telegram.org |
   | `SESSION_NAME` | Name of the Telethon session file (created in the project root whatever the current directory is, e.g. `telegram_saver`) |

   The file is chosen by the profile, the environment variable `TELEGRAM_SAVER_PROFILE`. Not set (default) uses
   `configs/.env` and `database/telegram_archive.db`; a value (e.g. `_dev_1`; letters, digits and `_` only) uses
   `configs/.env_dev_1` and `database/telegram_archive_dev_1.db`, which allows keeping separate accounts and databases.
   Set it before the start (PowerShell: `$env:TELEGRAM_SAVER_PROFILE = '_dev_1'`; PyCharm: *Run Configuration* →
   *Environment variables*). Run one profile at a time: they share `media_storage/`, `exported_messages/` and the port.
   Give each profile its own `SESSION_NAME`. All paths are built from the project root, so the application can be
   started from any directory.
6. **Run the application:**
   ```bash
   python telegram_saver.py
   ```
   or, equivalently:
   ```bash
   uvicorn web.main:app --host 127.0.0.1 --port 5000
   ```
   On the first start Telegram sends a login code (enter it in the console). If the code does not arrive, use
   `tools/telegram_qr_login.py` (login by QR code). Then open `http://localhost:5000` in your browser.

   Run with **one worker and without `--reload`**: every start logs in to Telegram and the application state is global.

   The server listens only on `127.0.0.1:5000` (`HOST` and `PORT` in `configs/config.py`) and rejects with 403 the
   requests addressed to another host, sent from another site (`Origin`) or marked `Sec-Fetch-Site: cross-site`, so a
   web page open in your browser cannot control the application. Open it at `http://127.0.0.1:5000` or
   `http://localhost:5000`; a reverse proxy or another port needs the same values in the config.
7. **Stop the application:** press `Ctrl+C` in the terminal. In the PyCharm *Run* window `Ctrl+C` does not reach the
   process: use the **Stop** button.

The session file (`*.session`), `configs/.env*`, the database (`*.db`) and `media_storage/` give access to your
account and data: never commit or share them.

## Usage

The page has two tabs:

- **Telegram**: the list of your chats (with filters by type and title) and the messages of the selected chat
  (filters by date and text). Check the messages you want and press **Save selection to database**: texts, media
  files and an HTML copy of the message are saved to the database and to `media_storage/`. Already saved messages are
  marked. Under each message a line summarizes its files, e.g. `2 Images, Video`.
- **Database**: the archive. Filter by chat, date, text and tags; open a message to see its details. Check messages
  to tag them (the tag buttons act on the checked messages), export them to HTML (`exported_messages/`) or delete
  them. The buttons that need checked messages are disabled until at least one message is checked.

The status bar at the bottom shows the progress and the result of every operation. Service operations (report of
files without records, recreation of lost message HTML files, re-download of missing media, backup) are in the
database maintenance menu.

## Database

### Current: SQLite

- **Pros**: zero configuration, a single file, suitable for personal use
- **Location**: `database/telegram_archive<PROFILE>.db`

### PostgreSQL

The schema is designed with SQLAlchemy ORM to be portable, but PostgreSQL is not supported yet: Telegram IDs do not
fit into `int32`, so the ID columns must first become `BigInteger` (see the roadmap).

## Tests
```bash
pytest
```
Telethon is mocked: the tests do not connect to Telegram.

## Roadmap

- [ ] Filter of archived messages without tags (to tag recently saved messages)
- [ ] Fully asynchronous `TelegramHandler` and async SQLAlchemy sessions instead of the global lock
- [ ] PostgreSQL and Alembic migrations (`BigInteger` ID columns)
- [ ] Source chats of "Saved Messages": list of chats and a filter by the original chat
- [ ] Download a video before saving, delete a message in Telegram itself
- [ ] Export to JSON/CSV/PDF, scheduled backups, Docker
- [ ] Multi-user mode (state per session instead of global)

## License

This project is licensed under the MIT License.

## Contact

**Sergiy Shypulin**

- Email: [s.shypulin@gmail.com](mailto:s.shypulin@gmail.com)
- LinkedIn: [linkedin.com/in/sergiy-shypulin](https://linkedin.com/in/sergiy-shypulin)
- GitHub: [@SShSoftwareEngineer](https://github.com/SShSoftwareEngineer)
