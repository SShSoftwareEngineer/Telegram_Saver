# Telegram Saver - Content Archive System

Flexible data extraction and storage system for Telegram content with manual and automated retrieval.

### Overview
Personal archive tool for selective Telegram content preservation. Built with async Python for efficient data 
handling and SQLAlchemy for database flexibility.

### Features
- **Flexible extraction**: Manual selection via "saved messages" + optional automatic channel monitoring
- **Multi-type content**: Messages, media files, documents, forward chains, user metadata
- **Database abstraction**: SQLAlchemy ORM with SQLite (easily portable to PostgreSQL)
- **Web interface**: Flask + Vanilla JavaScript for browsing and searching archived content
- **Async operations**: AsyncIO for non-blocking data retrieval

### Architecture
- **Backend**: Python, Telethon (Telegram API), AsyncIO
- **Database**: SQLite via SQLAlchemy ORM (PostgreSQL-ready schema)
- **Web UI**: Flask, Jinja2, Vanilla JavaScript
- **Data flow**: Telegram API → AsyncIO handlers → SQLAlchemy → Database → Flask views

### Use Cases
- Personal message archive (selective saving via Telegram "saved messages")
- Media library management with metadata
- Content backup with easy search and export
- Advanced search functionality
- Data analysis of saved conversations

### Project Stats
- 1,000+ messages archived
- 500+ media files organized
- Multiple content types supported
- Database schema ready for PostgreSQL migration

### Tech Highlights
- **Database design**: Normalized schema supporting easy PostgreSQL migration
- **Async architecture**: Non-blocking I/O for media downloads
- **ORM flexibility**: Single codebase supports SQLite (dev) and PostgreSQL (production)

### Future Enhancements
- PostgreSQL deployment for larger datasets
- Export to common formats (JSON, CSV, HTML)
- Automated scheduled backups

### Installation

1. Clone the repository:  
   git clone https://github.com/SShSoftwareEngineer/Telegram_Saver.git  
   cd Telegram_Saver
2. Install Poetry (if not already installed):
   ##### On Linux/macOS
   curl -sSL https://install.python-poetry.org | python3 -
   #### On Windows (PowerShell)
   (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -
3. Install the dependencies:  
   poetry install
3. Set up your Telegram API credentials in a .env file:    
   - Create a new application on [my.telegram.org](https://my.telegram.org)
   - Create a ".env" file in the project root  
   Add your API_ID, API_HASH and params to the .env file.
4. Run the script:  
   python telegram_saver.py  
   Navigate to `http://localhost:5000` in your browser.

### Usage

Run the script to start parsing job postings from Telegram channels.
The script automatically analyzes new vacancies and saves the information in a structured form in the database.

### Database

#### Current: SQLite

- **Pros**: Zero configuration, single file, perfect for personal use
- **Current capacity**: Handles 10K+ messages efficiently

#### PostgreSQL Migration Ready

The database schema is designed with SQLAlchemy ORM for easy migration:
```python
# Simply change connection string in config:
DATABASE_URL = "postgresql://user:password@localhost/telegram_archive"
```

Schema includes:
- Normalized structure for messages, users, media
- Foreign key relationships
- Indexes for common queries

### Roadmap

- [ ] PostgreSQL deployment for larger datasets
- [ ] Export to common formats (JSON, CSV, PDF)
- [ ] Automated scheduled backups with cron/scheduler
- [ ] AI-powered content analysis and tagging
- [ ] Multi-language support
- [ ] Docker containerization

### Under Consideration

- Integration with Apache Airflow for ETL automation
- REST API for programmatic access
- Cloud storage integration (S3, Google Drive)

### License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### Contact

**Sergiy Shypulin**

- Email: [s.shypulin@gmail.com](mailto:s.shypulin@gmail.com)
- LinkedIn: [linkedin.com/in/sergiy-shypulin](https://linkedin.com/in/sergiy-shypulin)
- GitHub: [@SShSoftwareEngineer](https://github.com/SShSoftwareEngineer)
