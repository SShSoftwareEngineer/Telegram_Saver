"""
Tests of the contract between the routes and the page script (`web/ui.py`): a successful response has only the
sections `html` and `checked`, empty entries are left out, the page script reads exactly these sections, shows the
errors in the status bar (no `alert`) and makes the pressed button busy for the time of its request.
Тесты контракта между роутами и скриптом страницы (`web/ui.py`): успешный ответ содержит только секции `html` и
`checked`, пустые записи опускаются, скрипт страницы читает именно эти секции, показывает ошибки в строке статуса
(без `alert`) и делает нажатую кнопку занятой на время ее запроса.
"""

from pathlib import Path
from fastapi.testclient import TestClient
from config import FormCfg
from web.ui import ui_content, ui_update

SCRIPT = Path(__file__).resolve().parent.parent / 'static' / 'js' / 'my_scripts.js'
STYLES = Path(__file__).resolve().parent.parent / 'static' / 'css' / 'styles.css'
SECTIONS = {'html', 'checked'}


def test_content_has_only_the_filled_sections():
    """Empty sections are not sent; an entry of `html` with `None` is dropped, an empty string is kept (it clears)"""
    assert ui_content() == {}
    assert ui_content({'a': None}, {}) == {}
    assert ui_content({'a': '', 'b': None, 'c': '<b>x</b>'}, {'box': False}) == {
        'html': {'a': '', 'c': '<b>x</b>'}, 'checked': {'box': False}}


def test_update_is_a_json_response_with_headers():
    """`ui_update` builds a JSON body of the contract and passes the extra headers on"""
    response = ui_update({'a': 'x'}, headers={'X-Test': '1'})
    assert response.body == b'{"html":{"a":"x"}}'
    assert response.headers['x-test'] == '1'


def test_routes_answer_by_the_contract(client: TestClient, db_handler, tg_handler):
    """A route of every kind (a page list, a filter, the status bar, the maintenance) answers with the known sections"""
    tg_handler.get_dialog_list.return_value = []
    responses = [client.get('/tg_dialogs'),
                 client.post('/db_message_apply_filters', data={}),
                 client.post('/db_tag_all_sorting', data={}),
                 client.get('/status_output')]
    for response in responses:
        assert response.status_code == 200
        body = response.json()
        assert set(body) <= SECTIONS, response.url
        assert all(isinstance(value, str) for value in body.get('html', {}).values())
    assert 'tg_dialogs' in responses[0].json()['html']
    assert FormCfg.db_detail_tags['all_detail_tags'] in responses[2].json()['html']


def test_error_has_the_error_key_and_no_sections(client: TestClient):
    """A failed response is `{"error": ...}` with a non-2xx status: the script tells it from an update by the status"""
    response = client.get('/no_such_url')
    assert response.status_code == 404
    assert response.json() == {'error': 'Not Found'}


def test_script_reads_the_sections_and_warns_about_others():
    """The script applies `html` and `checked` and warns about any other section"""
    script = SCRIPT.read_text(encoding='utf-8')
    body = script[script.index('function updateElementsFromResponse('):]
    body = body[:body.index('\n}\n')]
    assert 'data.html' in body and 'data.checked' in body
    assert "section !== 'html' && section !== 'checked'" in body


def test_script_shows_errors_in_the_status_bar_without_alert():
    """The failed requests go to the status bar through `showRequestError`; the script has no `alert` and no raw
    `fetch` outside `requestJSON` and the status poll"""
    script = SCRIPT.read_text(encoding='utf-8')
    code = '\n'.join(line for line in script.splitlines() if not line.lstrip().startswith('//'))
    assert 'alert(' not in code
    assert 'showRequestError(error)' in code and "getElementById('sb_operation')" in code
    assert code.count('fetch(') == 2  # `requestJSON` and the status poll
    assert 'data.error' in code


def test_script_makes_the_pressed_button_busy():
    """The button that sent a request is disabled with the `is-busy` class until the end of the request (also on an
    error); the buttons that depend on the checked items skip it when they are refreshed; the CSS draws a spinner"""
    script = SCRIPT.read_text(encoding='utf-8')
    assert "setButtonBusy(button, true)" in script and 'setButtonBusy(button, false)' in script
    body = script[script.index('async function requestJSON('):]
    body = body[:body.index('\n}\n')]
    assert 'finally' in body and body.index('finally') > body.index('catch')
    assert ':not(.is-busy)' in script
    for function in ('pressFormButton', 'callHandler'):
        part = script[script.index(f'function {function}('):]
        assert 'clickedButton()' in part[:part.index('\n}\n')], function
    assert 'button.is-busy::after' in STYLES.read_text(encoding='utf-8')
