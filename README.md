# Telegram Saver

## Being finalized

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
5. Copy the api_id and hash_id, received after registration, to the configs\.env file in the APP_API_ID and APP_API_HASH fields.
6. In the PHONE field, enter your phone number in international format with a "+" sign.
7. In the PASSWORD field, enter your password, if used.
8. Run the script telegram_saver.py
9. To open the application's web interface in your browser, follow the link http://127.0.0.1:5000
