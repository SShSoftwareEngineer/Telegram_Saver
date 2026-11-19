"""
Tests of the tag form of the database tab (`db_detail_tags.html`): the "Message Tags" list is filled automatically and has
no clear button, the other clear buttons and the "Update tag" buttons also clear the hidden old tag name, so a stale old
name is never renamed.
Тесты формы тегов вкладки БД (`db_detail_tags.html`): список «Message Tags» заполняется автоматически и не имеет кнопки
очистки, остальные кнопки очистки и кнопки «Update tag» очищают и скрытое старое имя тега, поэтому устаревшее старое имя
не переименовывается.
"""

import html
import re
from fastapi.testclient import TestClient
from configs.config import FormCfg

CFG = FormCfg.db_detail_tags
CLEAR_CALL = re.compile(r'onclick="((?:(?!onclick=)[^"])*?clearFormFields\(\[([^\]]*)\]\))')


def page_text(client: TestClient) -> str:
    """The page with the HTML entities in attributes decoded like a browser does / Страница с декодированными сущностями"""
    return html.unescape(client.get('/').text)


def all_clear_calls(page: str) -> list[list[str]]:
    """The ID lists of all `clearFormFields([...])` calls of the tag form / Списки ID всех вызовов очистки формы тегов"""
    start = page.index(f'id="{CFG["old_tag_name"]}"')
    return [re.findall(r"'([^']+)'", ids) for _, ids in CLEAR_CALL.findall(page[start:])]


def clear_calls(page: str) -> list[list[str]]:
    """The calls that clear the tag name (the edit field is among the IDs) / Вызовы, очищающие имя тега"""
    return [call for call in all_clear_calls(page) if CFG['edit_tag_name'] in call]


def test_message_tags_list_has_no_clear_button(client: TestClient):
    """The list of the open message tags has no clear button: it is filled automatically"""
    page = page_text(client)
    list_start = page.index(f'id="{CFG["curr_message_tags"]}"')
    list_end = page.index('Edit Tag Name', list_start)
    assert 'clear-button' not in page[list_start:list_end]
    assert 'class="control-X-button no-X-button"' in page[:list_start]


def test_tag_name_clear_calls_clear_the_old_name_and_the_message_tag(client: TestClient):
    """The clear button of the edit field and the two "Update tag" buttons clear the edit field, the hidden old name and
    the highlighted tag of the open message, but not the selection in "All tags" """
    calls = clear_calls(page_text(client))
    assert len(calls) == 3
    expected = {CFG['edit_tag_name'], CFG['old_tag_name'], CFG['curr_message_tags']}
    for call in calls:
        assert set(call) == expected


def test_all_tags_selection_is_cleared_only_by_its_own_button(client: TestClient):
    """The "All tags" list is cleared by its own button and by nothing else (it also serves the tag filter)"""
    calls = all_clear_calls(page_text(client))
    assert [call for call in calls if CFG['all_detail_tags'] in call] == [[CFG['all_detail_tags']]]


def test_the_old_name_field_is_a_hidden_input_known_to_the_script(client: TestClient):
    """The cleared old name is the hidden field the update routes read"""
    page = page_text(client)
    assert re.search(rf'<input type="hidden" id="{CFG["old_tag_name"]}" name="{CFG["old_tag_name"]}"', page)
