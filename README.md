# Telegram Saver

<details open>
  <summary>🇬🇧 English version</summary>

### Project Description

This project is designed to automate the process of parsing job postings from Telegram channels. The script
extracts key information from messages, follows hyperlinks to obtain full text of job announcements, retrieves
additional vacancy details, and stores data in a database. The solution is used for statistical analysis of job
market trends, vacancies and candidate requirements.

### Features

Automated Parsing – Extracts key job details from Telegram messages.  
Link Following – Retrieves full job descriptions from external sources.  
Data Storage & Analysis – Saves extracted data into a database SQLite for easy access and analysis.  
Market Trend Analysis – Provides insights into job market trends and candidate requirements.  
Export to Excel - Allows exporting parsed data to Excel for further processing.

### Tech Stack

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
Python - Core programming language.  
![Aiohttp](https://img.shields.io/badge/aiohttp-%232C5bb4.svg?style=for-the-badge&logo=aiohttp&logoColor=white)
AIOHTTP - Asynchronous HTTP client for fetching web content.  
![Pandas](https://img.shields.io/badge/pandas-%23150458.svg?style=for-the-badge&logo=pandas&logoColor=white)
Pandas - Data manipulation and analysis.  
![SQLite](https://img.shields.io/badge/sqlite-%2307405e.svg?style=for-the-badge&logo=sqlite&logoColor=white)
SQLite - Database for storing parsed data.  
![Microsoft Excel](https://img.shields.io/badge/Microsoft_Excel-217346?style=for-the-badge&logo=microsoft-excel&logoColor=white)
MS Excel - Analysis and visualization.  
SQLAlchemy - ORM for database interactions.  
Telethon - Library for interacting with Telegram API.  
BeautifulSoup - HTML parsing for extracting job details.    
RE (Regular Expressions) - Text pattern matching.  
Pydantic - Configuration File Validation.  
OpenPyXL - Excel file manipulation.

### Installation

1. Clone the repository:  
   git clone https://github.com/yourusername/job-posting-parser.git  
   cd job-posting-parser
2. Install the dependencies:  
   pip install -r requirements.txt
3. Set up your Telegram API credentials in a .env file:    
   Create a new application on my.telegram.org.  
   Add your API_ID, API_HASH and params to the .env file.
4. Run the script:  
   python job_posting_parser.py

### Usage

Run the script to start parsing job postings from Telegram channels.
The script automatically analyzes new vacancies and saves the information in a structured form in the database.

### Roadmap

It is planned to use artificial intelligence for detailed analysis of information in job vacancies and labor market
trends.

### License

This project is licensed under the MIT License.

### Contact

[shypulin@ukr.net](mailto:shypulin@ukr.net)

</details>

<details>
  <summary>🇷🇺 Русская версия</summary>

### Описание проекта

Проект предназначен для автоматизации обработки рассылок с вакансиями из определенных Telegram-каналов. Скрипт
извлекает ключевую информацию из сообщений, переходит по ссылкам для получения полных текстов объявлений,
производит их парсинг и сохраняет данные в базу данных для дальнейшего анализа. Решение полезно для статистического
анализа тенденций на рынке труда, вакансий и требований к кандидатам.

### Функциональность

Автоматический парсинг – Извлекает ключевые данные о вакансиях из сообщений в Telegram.  
Переход по ссылкам – Получает полные тексты объявлений.  
Сохранение и анализ данных – Сохраняет информацию в базу данных SQLite для удобного доступа и анализа.  
Анализ рынка труда – Позволяет исследовать тенденции рынка вакансий.  
Экспорт в Excel - Позволяет экспортировать данные в Excel для дальнейшей обработки.

### Используемые технологии

![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
Python - Основной язык программирования.  
![Aiohttp](https://img.shields.io/badge/aiohttp-%232C5bb4.svg?style=for-the-badge&logo=aiohttp&logoColor=white)
AIOHTTP - Асинхронный HTTP-клиент для получения веб-контента.  
![Pandas](https://img.shields.io/badge/pandas-%23150458.svg?style=for-the-badge&logo=pandas&logoColor=white)
Pandas - Манипуляции и анализ данных.  
![SQLite](https://img.shields.io/badge/sqlite-%2307405e.svg?style=for-the-badge&logo=sqlite&logoColor=white)
SQLite - База данных для хранения извлеченной информации.  
![Microsoft Excel](https://img.shields.io/badge/Microsoft_Excel-217346?style=for-the-badge&logo=microsoft-excel&logoColor=white)
MS Excel - Анализ и визуализация.  
SQLAlchemy - ORM для взаимодействия с базой данных.  
Telethon - Библиотека для работы с API Telegram.  
BeautifulSoup - Парсинг HTML для извлечения деталей вакансий.  
RE (Регулярные выражения) - Поиск текстовых шаблонов.  
Pydantic - Валидация файла конфигурации.  
OpenPyXL - Работа с файлами Excel.

### Установка

1. Клонируйте репозиторий:  
   git clone https://github.com/yourusername/job-posting-parser.git  
   cd job-posting-parser
2. Настройте учетные данные API Telegram:  
   pip install -r requirements.txt
3. Настройте API Telegram в файле .env:  
   Создайте новое приложение на my.telegram.org.  
   Добавьте ваш API_ID, API_HASH и другие параметры в файл .env.
4. Запустите скрипт:  
   python job_posting_parser.py

### Использование

Запустите скрипт, чтобы начать парсинг вакансий из каналов Telegram.
Скрипт автоматически анализирует новые вакансии и сохраняет информацию в структурированном виде в базе данных.

### Планы по развитию

Планируется использовать искусственный интеллект для детального анализа информации в вакансии и тенденций рынка труда.

### Лицензия

Этот проект лицензирован под MIT License.

### Контакты

[shypulin@ukr.net](mailto:shypulin@ukr.net)

</details>


Instruction for setting up and running the application:

1. Create a new project by cloning from the repository
   https://github.com/SShSoftwareEngineer/Telegram_Saver.git
2. Create a virtual environment and activate it. For Windows, use the following commands:
   python -m venv your_venv_name
   your_venv_name\Scripts\activate
   Commands can be entered in the IDE terminal.
3. To install the required modules, enter the command
   pip install -r requirements.txt
4. Creating your Telegram Application by following the instructions at
   https://core.telegram.org/api/obtaining_api_id
5. Copy the api_id and hash_id, received after registration, to the configs\.env file in the APP_API_ID and APP_API_HASH
   fields.
6. In the PHONE field, enter your phone number in international format with a "+" sign.
7. In the PASSWORD field, enter your password, if used.
8. Run the script telegram_saver.py
9. To open the application's web interface in your browser, follow the link http://127.0.0.1:5000
