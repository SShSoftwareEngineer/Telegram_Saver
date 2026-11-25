"""
Tests of the launcher: the check of the port before the start.
Тесты запускателя: проверка порта перед запуском.
"""

import socket
import pytest
import telegram_handler
import telegram_saver
from telegram_saver import ensure_port_free


def test_free_port_passes():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    ensure_port_free('127.0.0.1', port)  # No exception: the port was released / Порт освобожден


def test_taken_port_stops_the_start_with_a_clear_message():
    with socket.socket() as holder:
        holder.bind(('127.0.0.1', 0))
        holder.listen()
        port = holder.getsockname()[1]
        with pytest.raises(SystemExit, match=f'Port {port}.*another copy|Another copy'):
            ensure_port_free('127.0.0.1', port)


def test_another_account_is_a_short_message_without_starting_the_server(monkeypatch: pytest.MonkeyPatch):
    """The wrong account of the profile ends the start with a message: no traceback, the server is not run"""
    def wrong_account():
        raise telegram_handler.ProfileAccountError('The profile belongs to another account')

    monkeypatch.setenv('TELEGRAM_SAVER_PROFILE', 'test')
    monkeypatch.setattr(telegram_saver, 'choose_profile', lambda *_: 'test')
    monkeypatch.setattr(telegram_saver, 'ensure_port_free', lambda *_: None)
    monkeypatch.setattr(telegram_handler, 'get_tg_handler', wrong_account)
    started = []
    monkeypatch.setattr('uvicorn.run', lambda *args, **kwargs: started.append(True))
    with pytest.raises(SystemExit, match='belongs to another account'):
        telegram_saver.main()
    assert not started
