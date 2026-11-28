"""
Tests of the buttons that act on the checked messages: they are rendered disabled and marked with the selector of the
checkboxes they wait for (the script enables them while a message is checked); the buttons that do not depend on the
checked messages are not marked.
Тесты кнопок, действующих на отмеченные сообщения: они отрисованы неактивными и помечены селектором чек-боксов, которых
ждут (скрипт включает их, пока отмечено сообщение); кнопки, не зависящие от отмеченных сообщений, не помечены.
"""

import re
from fastapi.testclient import TestClient

TG_CHECKBOX = '.tg-message-checkbox'
DB_CHECKBOX = '.db-message-checkbox'


def buttons(page: str) -> list[str]:
    """Opening tags of all buttons of the page / Открывающие теги всех кнопок страницы"""
    return re.findall(r'<button\b[^>]*>', page, re.S)


def marked(page: str) -> list[str]:
    """Opening tags of the buttons that wait for a checked item / Теги кнопок, ожидающих отмеченный элемент"""
    return [tag for tag in buttons(page) if 'data-needs-checked' in tag]


def test_checked_buttons_are_disabled_on_load(client: TestClient):
    """Every marked button starts disabled: nothing is checked on a fresh page"""
    page = client.get('/').text
    tags = marked(page)
    assert tags
    for tag in tags:
        assert re.search(r'\bdisabled\b', tag), tag


def test_save_button_of_telegram_waits_for_telegram_checkboxes(client: TestClient):
    """The button "Do it" (save / delete / both, see `doTgAction`) waits for the Telegram checkboxes"""
    page = client.get('/').text
    save = [tag for tag in marked(page) if 'doTgAction(' in tag]
    assert len(save) == 1
    assert f'data-needs-checked="{TG_CHECKBOX}"' in save[0]


def test_database_buttons_wait_for_database_checkboxes(client: TestClient):
    """Export, delete and the three tag buttons that act on the checked messages wait for the database checkboxes"""
    page = client.get('/').text
    routes = ['/db_export_selected_message_to_html', '/db_delete_selected_from_database', '/db_tag_add',
              '/db_tag_remove', '/db_tag_update\'']
    for route in routes:
        found = [tag for tag in marked(page) if route in tag]
        assert len(found) == 1, route
        assert f'data-needs-checked="{DB_CHECKBOX}"' in found[0], route
    assert len([tag for tag in marked(page) if DB_CHECKBOX in tag]) == len(routes)


def test_buttons_that_do_not_need_checked_messages_are_not_marked(client: TestClient):
    """"Update tag everywhere", the selection buttons and the filter buttons work without checked messages"""
    page = client.get('/').text
    for tag in buttons(page):
        if any(route in tag for route in ('/db_tag_update_everywhere', 'selectAllCB', 'deSelectAllCB',
                                          'invertSelectionCB', 'apply_filters')):
            assert 'data-needs-checked' not in tag, tag
            assert not re.search(r'\bdisabled\b', tag), tag
