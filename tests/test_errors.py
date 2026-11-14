"""
Tests of the JSON error handlers.
Тесты JSON-обработчиков ошибок.
"""

from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from database_handler import DatabaseHandler
from utils import status_messages
from web.main import app


@pytest.fixture
def failing_routes():
    """
    Temporary routes that fail on purpose; they are removed after the test so other tests do not see them.
    Временные маршруты, которые падают намеренно; после теста они удаляются, чтобы другие тесты их не видели.
    """
    routes_before = list(app.router.routes)

    @app.get('/_test_boom')
    def boom():
        raise RuntimeError('<b>boom</b>')

    @app.get('/_test_number/{value}')
    def number(value: int):
        return {'value': value}

    yield
    app.router.routes[:] = routes_before


def test_unknown_url_returns_json(client: TestClient):
    """404 for an unknown URL is JSON / 404 для неизвестного URL - JSON"""
    response = client.get('/no_such_url')
    assert response.status_code == 404
    assert response.json() == {'error': 'Not Found'}


def test_method_not_allowed_returns_json(client: TestClient):
    """405 keeps its Allow header and is JSON / 405 сохраняет заголовок Allow и отдается в JSON"""
    response = client.post('/status_output')
    assert response.status_code == 405
    assert 'error' in response.json()
    assert 'GET' in response.headers['allow']


@pytest.mark.usefixtures('failing_routes')
def test_validation_error_returns_json(client: TestClient):
    """422 has the same `error` key and the field details / 422 с тем же ключом `error` и деталями по полю"""
    response = client.get('/_test_number/abc')
    assert response.status_code == 422
    body = response.json()
    assert body['error'] == 'Invalid request'
    assert body['detail'][0]['loc'][-1] == 'value'


@pytest.mark.usefixtures('failing_routes')
def test_unhandled_error_returns_json_and_updates_status(error_client: TestClient):
    """An unhandled exception gives 500 in JSON and an escaped message in the status bar"""
    status_messages.mess_update('', '', new_list=True)
    response = error_client.get('/_test_boom')
    assert response.status_code == 500
    assert response.json() == {'error': 'RuntimeError: <b>boom</b>'}
    status = error_client.get('/status_output').json()
    assert '/_test_boom' in status['sb_operation']
    assert 'RuntimeError: &lt;b&gt;boom&lt;/b&gt;' in status['sb_report']
    assert '<b>boom</b>' not in status['sb_report']


@pytest.mark.usefixtures('failing_routes')
def test_unhandled_error_rolls_back_session(error_client: TestClient, db_handler: DatabaseHandler, monkeypatch):
    """The handler rolls the shared database session back / Обработчик откатывает общую сессию БД"""
    rollback = MagicMock(wraps=db_handler.session.rollback)
    monkeypatch.setattr(db_handler.session, 'rollback', rollback)
    assert error_client.get('/_test_boom').status_code == 500
    rollback.assert_called_once()


@pytest.mark.usefixtures('failing_routes')
def test_unhandled_error_survives_rollback_failure(error_client: TestClient, db_handler: DatabaseHandler, monkeypatch):
    """A failing rollback does not break the error response / Сбой отката не ломает ответ с ошибкой"""
    monkeypatch.setattr(db_handler.session, 'rollback', MagicMock(side_effect=RuntimeError('rollback failed')))
    response = error_client.get('/_test_boom')
    assert response.status_code == 500
    assert response.json()['error'].startswith('RuntimeError')
