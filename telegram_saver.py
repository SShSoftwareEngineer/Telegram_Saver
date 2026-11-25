"""
Application launcher: chooses the profile and runs the FastAPI app (`web.main:app`) with uvicorn on
http://127.0.0.1:5000.
Run: `python telegram_saver.py [--profile <profile name>]` (one worker, no reload: every start logs in to Telegram).
The profile: the argument, the environment variable `TELEGRAM_SAVER_PROFILE`, the only existing profile, otherwise
a menu in the console (also the creation of a new profile).
Запускатель приложения: выбирает профиль и запускает приложение FastAPI (`web.main:app`) через uvicorn на
http://127.0.0.1:5000.
Запуск: `python telegram_saver.py [--profile <имя профиля>]` (один воркер, без reload: каждый старт входит в Telegram).
Профиль: аргумент, переменная окружения `TELEGRAM_SAVER_PROFILE`, единственный существующий профиль, иначе меню
в консоли (там же создание нового профиля).
"""

import os
import socket
import sys

from profiles import PROFILE_ENV_VAR, choose_profile


def ensure_port_free(host: str, port: int) -> None:
    """
    Stops the start with a clear message if the port is taken. uvicorn binds the port only after the startup of the
    application (the login to Telegram and the loading of the chats), so without this check the error appears late
    and looks like a failure of the application. The usual reason is a copy of the application that is still running
    (for example after the Stop button in PyCharm).
    Останавливает запуск с понятным сообщением, если порт занят. uvicorn занимает порт только после запуска
    приложения (вход в Telegram и загрузка чатов), поэтому без этой проверки ошибка появляется поздно и выглядит как
    сбой приложения. Обычная причина - еще работающая копия приложения (например, после кнопки Stop в PyCharm).
    """

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if sys.platform != 'win32':  # As uvicorn does; on Windows it would hide a port that is in use
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError as error:
            raise SystemExit(f'Port {port} on {host} is not available ({error}). Either another copy of the '
                             f'application '
                             f'is still running (Task Manager, python.exe), or Windows has reserved the port '
                             f'(WinError 10013; see `netsh interface ipv4 show excludedportrange protocol=tcp`): '
                             f'change PORT in config.py\n'
                             f'Порт {port} на {host} недоступен ({error}). Либо еще работает другая копия '
                             f'приложения (Диспетчер задач, python.exe), либо Windows зарезервировала порт '
                             f'(WinError 10013; см. `netsh interface ipv4 show excludedportrange protocol=tcp`): '
                             f'измените PORT в config.py') from error


def main() -> None:
    """
    Chooses the profile, passes it to `config` through the environment variable and runs the server. The application
    is imported only after that: `config` reads the profile when it is imported.
    Выбирает профиль, передает его в `config` через переменную окружения и запускает сервер. Приложение
    импортируется только после этого: `config` читает профиль при импорте.
    """

    os.environ[PROFILE_ENV_VAR] = choose_profile(sys.argv[1:], os.environ)
    import uvicorn
    from config import HOST, PORT
    ensure_port_free(HOST, PORT)
    from telegram_handler import ProfileAccountError, get_tg_handler
    try:
        # The login happens here, not in the startup of the application: a failure of the startup is logged by uvicorn
        # as a long traceback, and a wrong account has to be a short message
        # Вход выполняется здесь, а не при запуске приложения: сбой запуска uvicorn выводит длинной трассировкой, а
        # чужой аккаунт должен быть коротким сообщением
        get_tg_handler()
    except ProfileAccountError as error:
        raise SystemExit(str(error)) from None
    from web.main import app
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == '__main__':
    main()
