"""
TEMPORARY: compares the JSON of the migrated routes with the Flask version (`legacy_flask.py`) on the same fake state.
Delete this file together with Flask (step 12 of MIGRATION_PLAN.md).
ВРЕМЕННО: сравнивает JSON перенесенных роутов с Flask-версией (`legacy_flask.py`) на одном и том же состоянии-заглушке.
Удалить вместе с Flask (шаг 12 MIGRATION_PLAN.md).
"""

import sys
from collections.abc import Iterator
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from configs.config import FormCfg
from tests.test_telegram_routes import CHANNEL_ID, make_details, make_dialog, make_message_group


@pytest.fixture
def flask_client(tg_handler: SimpleNamespace, db_handler) -> Iterator:
    """
    Flask test client. The module is imported while the fake handlers are installed (it takes them on import) and is
    removed afterwards, so the next test imports it again with its own fakes.
    Тестовый клиент Flask. Модуль импортируется, пока установлены заглушки обработчиков (он берет их при импорте), и
    затем удаляется, чтобы следующий тест импортировал его заново со своими заглушками.
    """
    sys.modules.pop('legacy_flask', None)
    import legacy_flask  # pylint: disable=import-outside-toplevel
    yield legacy_flask.tg_saver.test_client()
    sys.modules.pop('legacy_flask', None)


def reset_state(tg_handler: SimpleNamespace) -> None:
    """The same starting state for both applications / Одинаковое начальное состояние для обоих приложений"""
    tg_handler.current_state.dialog_list = [make_dialog()]
    tg_handler.current_state.selected_dialog_id = CHANNEL_ID
    tg_handler.current_state.message_group_list = [make_message_group()]
    tg_handler.current_state.message_details = None
    tg_handler.get_dialog_list.return_value = [make_dialog(), make_dialog(42, 'Друг <b>&')]
    tg_handler.get_message_group_list.return_value = [make_message_group(number=1), make_message_group(number=2)]
    tg_handler.get_message_detail.return_value = make_details()


DIALOG_FORM = {FormCfg.tg_dialog_filter['sorting_field']: '0', FormCfg.tg_dialog_filter['sorting_order']: '1',
               FormCfg.tg_dialog_filter['dialog_type']: '2', FormCfg.tg_dialog_filter['dialog_title_query']: 'chat'}
MESSAGE_FORM = {FormCfg.tg_message_filter['sorting_order']: '1', FormCfg.tg_message_filter['date_from']: '2026-01-01',
                FormCfg.tg_message_filter['date_to']: '2026-02-01', FormCfg.tg_message_filter['message_query']: 'hi'}

CASES = [
    ('GET', '/', None),
    ('GET', '/tg_dialogs', None),
    ('GET', f'/tg_messages/{CHANNEL_ID}', None),
    ('GET', '/tg_messages/987654321', None),
    ('GET', f'/tg_details/{CHANNEL_ID}/{CHANNEL_ID}_1', None),
    ('POST', '/tg_dialog_apply_filters', DIALOG_FORM),
    ('POST', '/tg_dialog_apply_filters', None),
    ('POST', '/tg_message_apply_filters', MESSAGE_FORM),
    ('POST', '/tg_message_apply_filters', None),
]


@pytest.mark.parametrize(('method', 'url', 'form'), CASES, ids=[f'{m} {u}' for m, u, _ in CASES])
def test_matches_flask(client: TestClient, flask_client, tg_handler: SimpleNamespace, method: str, url: str,
                       form: dict | None):
    """The response status and JSON are the same as in Flask (the only difference: the test host name)"""
    reset_state(tg_handler)
    flask_response = flask_client.open(url, method=method, data=form)
    flask_state = (tg_handler.current_state.selected_dialog_id, tg_handler.current_state.message_details is None)
    reset_state(tg_handler)
    response = client.request(method, url, data=form)
    state = (tg_handler.current_state.selected_dialog_id, tg_handler.current_state.message_details is None)

    assert response.status_code == flask_response.status_code == 200
    # The same state changes / Одинаковые изменения состояния
    assert state == flask_state
    if url == '/':
        assert response.text == flask_response.get_data(as_text=True)
        return
    flask_json = flask_response.get_json()
    json = response.json()
    assert set(json) == set(flask_json)
    for key, value in json.items():
        # Flask test client host is `localhost`, Starlette one is `testserver` / Хост Flask - localhost, Starlette - testserver
        assert value.replace('http://testserver', 'http://localhost') == flask_json[key], key
