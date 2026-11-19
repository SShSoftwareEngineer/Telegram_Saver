"""
Tests of the scroll reset of the lists: the buttons that load a new list (the three filters) ask the script to start
the filled areas from the top, the buttons that change the same list (save, delete, tags) do not, so the position is
kept there; the script itself (`loadURL`, `pressFormButton`, `updateElementsFromResponse`) passes the flag on.
Тесты сброса прокрутки списков: кнопки, загружающие новый список (три фильтра), просят скрипт начать заполняемые области
с начала, кнопки, меняющие тот же список (сохранение, удаление, теги), не просят, поэтому положение там сохраняется;
сам скрипт (`loadURL`, `pressFormButton`, `updateElementsFromResponse`) передает флаг дальше.
"""

import html
import html
import re
from pathlib import Path
from fastapi.testclient import TestClient

SCRIPT = Path(__file__).resolve().parent.parent / 'static' / 'js' / 'my_scripts.js'
FILTER_ROUTES = ('/tg_dialog_apply_filters', '/tg_message_apply_filters', '/db_message_apply_filters')
SAME_LIST_ROUTES = ('/tg_save_selected_message_to_db', '/db_export_selected_message_to_html',
                    '/db_delete_selected_from_database', '/db_tag_add', '/db_tag_remove', '/db_tag_update')


def press_calls(page: str, route: str) -> list[str]:
    """The `pressFormButton`/`deleteSelectedButton` calls of the page that use the route / Вызовы кнопок с маршрутом"""
    return re.findall(rf"(?:pressFormButton|deleteSelectedButton)\([^\n]*?'{route}'(?:, true)?\)", html.unescape(page))


def test_filter_buttons_reset_the_scroll(client: TestClient):
    """The three filter buttons pass `true` as the scroll reset flag"""
    page = client.get('/').text
    for route in FILTER_ROUTES:
        calls = press_calls(page, route)
        assert len(calls) == 1, route
        assert calls[0].endswith(f"'{route}', true)"), calls[0]


def test_buttons_that_change_the_same_list_keep_the_scroll(client: TestClient):
    """Save, export, delete and the tag buttons do not reset the scroll"""
    page = client.get('/').text
    for route in SAME_LIST_ROUTES:
        calls = press_calls(page, route)
        assert len(calls) == 1, route
        assert 'true' not in calls[0], calls[0]


def test_script_passes_the_scroll_flag_on():
    """`loadURL` always resets, `pressFormButton` passes its flag, and the reset touches only the scroll areas"""
    script = SCRIPT.read_text(encoding='utf-8')
    assert 'function updateElementsFromResponse(data, resetScroll = false)' in script
    assert 'function pressFormButton(config, url, resetScroll = false)' in script
    assert 'updateElementsFromResponse(data, resetScroll)' in script
    assert 'updateElementsFromResponse(data, true)' in script
    assert "resetScroll && element.classList.contains('scroll')" in script
