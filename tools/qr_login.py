"""
One-off Telegram login via QR code. Use it when the login code does not arrive (SMS / in-app message).
It creates the same .session file the application uses, so the app will not ask for a code afterwards.
Разовый вход в Telegram по QR-коду. Используется, когда код входа не приходит (SMS / сообщение в приложении).
Создает тот же файл .session, что использует приложение, поэтому код после этого запрашиваться не будет.

Usage / Запуск (from any folder / из любой папки):
    poetry run pip install qrcode
    poetry run python tools/qr_login.py
Then in the Telegram app: Settings -> Devices -> Link Desktop Device -> scan the QR from the console.
Затем в приложении Telegram: Настройки -> Устройства -> Подключить устройство -> отсканировать QR из консоли.
The cloud (2FA) password, if enabled, is asked in the console and is never stored.
Облачный пароль (2FA), если он включен, запрашивается в консоли и нигде не сохраняется.
Do not share the QR code or the tg://login link: it is a one-time login to the account.
Не показывайте QR-код и ссылку tg://login никому: это одноразовый вход в аккаунт.
"""

import asyncio
import os
import sys
from getpass import getpass
from pathlib import Path

# The session file name is relative, so work from the project root as the application does
# Имя файла сессии относительное, поэтому работаем из корня проекта, как и приложение
PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import dotenv_values  # noqa: E402
from telethon import TelegramClient  # noqa: E402
from telethon.errors import SessionPasswordNeededError, PasswordHashInvalidError  # noqa: E402
from configs.config import ProjectDirs  # noqa: E402

try:
    import qrcode
except ImportError:
    sys.exit('Install the QR library first / Сначала установите библиотеку QR:  poetry run pip install qrcode')

MAX_PASSWORD_ATTEMPTS = 3  # Too many wrong passwords cause a temporary Telegram limit / Частые ошибки включают лимит


def show_qr(url: str) -> None:
    """
    Prints the QR code with the login link to the console.
    Выводит в консоль QR-код со ссылкой для входа.
    """

    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make()
    qr.print_ascii(invert=True)


async def ask_password(client: TelegramClient) -> None:
    """
    Asks for the cloud password in the console and signs in; stops after several wrong attempts.
    Запрашивает облачный пароль в консоли и входит; останавливается после нескольких неверных попыток.
    """

    for attempt in range(1, MAX_PASSWORD_ATTEMPTS + 1):
        try:
            await client.sign_in(password=getpass('Telegram cloud (2FA) password: '))
            return
        except PasswordHashInvalidError:
            print(f'Wrong password ({attempt}/{MAX_PASSWORD_ATTEMPTS}).')
    sys.exit('Too many wrong passwords, stopping / Слишком много неверных паролей, остановка.')


async def main() -> None:
    """
    Logs in by QR code and saves the session file.
    Выполняет вход по QR-коду и сохраняет файл сессии.
    """

    cfg = dotenv_values(ProjectDirs.telegram_settings_file)
    client = TelegramClient(cfg['SESSION_NAME'], int(cfg['API_ID']), cfg['API_HASH'])
    await client.connect()
    if await client.is_user_authorized():
        print('Already authorized, nothing to do / Уже авторизован, делать нечего.')
        await client.disconnect()
        return
    qr_login = await client.qr_login()
    while True:
        print('\nTelegram app -> Settings -> Devices -> Link Desktop Device -> scan this QR:\n')
        show_qr(qr_login.url)
        try:
            await qr_login.wait(timeout=60)
            break
        except asyncio.TimeoutError:
            await qr_login.recreate()  # The QR expires every ~30-60 s / QR устаревает каждые ~30-60 с
        except SessionPasswordNeededError:
            await ask_password(client)
            break
    me = await client.get_me()
    print('Logged in as / Вход выполнен:', me.first_name, '| session saved / сессия сохранена')
    await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
