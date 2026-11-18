"""
Tests of the operation mark in the status bar: a spinner while the operation runs, a check mark when it is over, a cross
on an error.
Тесты значка операции в строке статуса: крутилка во время работы, галочка по завершении, крестик при ошибке.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from utils import OPERATION_DONE, OPERATION_ERROR, OPERATION_RUNNING, StatusMessages, status_messages
import web.main as web_main
from web.main import app


@pytest.fixture
def status_routes():
    """
    Temporary routes with different outcomes; removed after the test / Временные роуты с разным исходом
    """
    routes_before = list(app.router.routes)

    @app.get('/_test_ok')
    def ok():
        status_messages.mess_update('Test job', 'working', new_list=True)
        status_messages.mess_update('', 'still working')
        return {'ok': True}

    @app.get('/_test_silent')
    def silent():
        return {'ok': True}

    @app.get('/_test_bad_request')
    def bad_request():
        status_messages.mess_update('Test job', 'rejected', new_list=True)
        raise HTTPException(status_code=400, detail='bad')

    @app.get('/_test_boom_status')
    def boom_status():
        status_messages.mess_update('Test job', 'about to fail', new_list=True)
        raise RuntimeError('boom')

    yield
    app.router.routes[:] = routes_before


def test_new_operation_is_running():
    """An update marks the operation as running: the spinner is right after the label, before the text"""
    status = StatusMessages()
    status.mess_update('Loading <b>', 'start', new_list=True)
    assert status.state == OPERATION_RUNNING
    html = status.messages['sb_operation']
    assert html.startswith('<strong>Operation: </strong><span class="sb-spinner"')
    assert html.endswith('Loading &lt;b&gt;')
    assert '✅' not in html and '❌' not in html


def test_finish_marks_done_and_error():
    """`finish` replaces the spinner with a check mark or a cross and keeps the text and the reports"""
    status = StatusMessages()
    status.mess_update('Job', 'line', new_list=True)
    reports = status.messages['sb_report']
    status.finish()
    assert status.state == OPERATION_DONE
    assert '✅' in status.messages['sb_operation'] and 'sb-spinner' not in status.messages['sb_operation']
    assert status.messages['sb_operation'].endswith('Job')
    assert status.messages['sb_report'] == reports
    status.finish(error=True)
    assert status.state == OPERATION_ERROR
    assert '❌' in status.messages['sb_operation'] and '✅' not in status.messages['sb_operation']


def test_finish_raises_version_only_on_change():
    """The page redraws the title when the mark changes, and not when `finish` changes nothing"""
    status = StatusMessages()
    status.finish()  # no operation yet / операции еще нет
    assert status.version == 0 and status.messages == {}
    status.mess_update('Job', 'line', new_list=True)
    version = status.version
    status.finish()
    assert status.version == version + 1
    status.finish()  # already marked / уже отмечено
    assert status.version == version + 1


def test_update_after_finish_runs_again():
    """The next operation shows the spinner again / Следующая операция снова показывает крутилку"""
    status = StatusMessages()
    status.mess_update('Job', 'line', new_list=True)
    status.finish()
    status.mess_update('Next job', 'line', new_list=True)
    assert status.state == OPERATION_RUNNING
    assert 'sb-spinner' in status.messages['sb_operation']


def test_startup_operation_is_finished(tg_handler, db_handler, monkeypatch: pytest.MonkeyPatch):
    """The handlers load the chat lists while the application starts (outside any request): the spinner of that
    operation must not stay after the startup / Обработчики грузят списки чатов при старте (вне запроса): крутилка этой
    операции не должна остаться после старта"""
    def loading_handler():
        status_messages.mess_update('Loading chat lists', '3 chats loaded', True)
        return db_handler

    monkeypatch.setattr(web_main, 'get_db_handler', loading_handler)
    with TestClient(app):
        assert status_messages.state == OPERATION_DONE
        assert '✅' in status_messages.messages['sb_operation']


@pytest.mark.usefixtures('status_routes')
def test_route_with_status_gets_check_mark(client: TestClient):
    """The middleware finishes the operation of a successful request / Успешный запрос завершает операцию"""
    assert client.get('/_test_ok').status_code == 200
    html = client.get('/status_output').json()['sb_operation']
    assert '✅' in html and 'Test job' in html and 'sb-spinner' not in html


@pytest.mark.usefixtures('status_routes')
def test_route_without_status_leaves_it_alone(client: TestClient):
    """A route that does not touch the status bar, and the status poll, change nothing, including the version"""
    status_messages.mess_update('Earlier job', 'line', new_list=True)
    version = status_messages.version
    assert client.get('/_test_silent').status_code == 200
    assert client.get('/status_output').status_code == 200
    assert status_messages.version == version
    assert status_messages.state == OPERATION_RUNNING


@pytest.mark.usefixtures('status_routes')
def test_error_response_gets_cross(client: TestClient):
    """An error response (here 400) after an update gives a cross / Ответ с ошибкой дает крестик"""
    assert client.get('/_test_bad_request').status_code == 400
    html = client.get('/status_output').json()['sb_operation']
    assert '❌' in html and 'Test job' in html


@pytest.mark.usefixtures('status_routes')
def test_exception_gets_cross_from_handler(error_client: TestClient):
    """After an unhandled exception the cross stays: the 500 handler (outside the middleware) does not make the
    operation running again / После необработанного исключения крестик остается"""
    assert error_client.get('/_test_boom_status').status_code == 500
    assert status_messages.state == OPERATION_ERROR
    html = error_client.get('/status_output').json()['sb_operation']
    assert '❌' in html and 'sb-spinner' not in html and '/_test_boom_status' in html
