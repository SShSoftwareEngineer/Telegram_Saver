"""
Tests of the multiple selection in the "All tags" list: the list accepts several tags, both tag lists fill the tag name
fields through one script function, and the filter button adds the selected tags (the script itself is checked in the
browser: there is no JavaScript runner in the tests).
Тесты множественного выбора в списке «All tags»: список принимает несколько тегов, оба списка тегов заполняют поля имени
тега одной функцией скрипта, а кнопка фильтра добавляет выбранные теги (сам скрипт проверяется в браузере: запуска
JavaScript в тестах нет).
"""

import html
import re
from pathlib import Path
from fastapi.testclient import TestClient
from config import FormCfg

CFG = FormCfg.db_detail_tags
SCRIPT = Path(__file__).resolve().parent.parent / 'static' / 'js' / 'my_scripts.js'


def select_tag(page: str, field: str) -> str:
    """The opening `<select>` tag of the field / Открывающий тег `<select>` поля"""
    match = re.search(rf'<select[^>]*id="{field}"[^>]*>', html.unescape(page), re.S)
    assert match, field
    return match.group(0)


def test_all_tags_list_allows_several_tags(client: TestClient):
    """Only the "All tags" list is multiple; the list of the open message tags stays a single choice"""
    page = client.get('/').text
    assert re.search(r'\bmultiple\b', select_tag(page, CFG['all_detail_tags']))
    assert not re.search(r'\bmultiple\b', select_tag(page, CFG['curr_message_tags']))


def test_both_lists_fill_the_name_fields_through_one_function(client: TestClient):
    """Both lists call `selectTagForEdit` with the edit field and the hidden old name"""
    page = client.get('/').text
    call = f"selectTagForEdit(this, '{CFG['edit_tag_name']}', '{CFG['old_tag_name']}')"
    for field in (CFG['all_detail_tags'], CFG['curr_message_tags']):
        assert call in select_tag(page, field)


def test_the_clear_button_of_all_tags_stays(client: TestClient):
    """The button that clears the selection of the "All tags" list stays (it drops several selected tags at once)"""
    page = html.unescape(client.get('/').text)
    assert f"clearFormFields(['{CFG['all_detail_tags']}'])" in page


def test_filter_button_waits_for_a_selected_tag(client: TestClient):
    """"Add tags to filter by tags" starts disabled and waits for a selection in the "All tags" list"""
    page = html.unescape(client.get('/').text)
    buttons = [tag for tag in re.findall(r'<button\b[^>]*>', page, re.S) if 'addTagToFilterFromAllTags' in tag]
    assert len(buttons) == 1
    assert re.search(r'\bdisabled\b', buttons[0])
    assert f'data-needs-selected="{CFG["all_detail_tags"]}"' in buttons[0]


def test_script_updates_the_buttons_when_the_selection_changes():
    """The script refreshes the buttons that need a selected row on a selection change, a clear and a response"""
    script = SCRIPT.read_text(encoding='utf-8')
    assert "querySelectorAll('[data-needs-selected]')" in script
    for function in ('selectTagForEdit', 'clearFormFields', 'updateElementsFromResponse'):
        body = script[script.index(f'function {function}('):]
        body = body[:body.index('\n}\n')]
        assert 'updateCheckedDependentButtons()' in body, function


def test_adding_to_the_filter_clears_the_selection():
    """After adding (also when every selected tag is already in the field) the selection of the list is cleared"""
    script = SCRIPT.read_text(encoding='utf-8')
    body = script[script.index('function addTagToFilterFromAllTags('):]
    body = body[:body.index('\n}\n')]
    assert body.count('clearFormFields([selectId])') == 2


def test_script_has_the_multiple_selection_functions():
    """The script reads all selected rows and no longer only the first one"""
    script = SCRIPT.read_text(encoding='utf-8')
    assert 'function getSelectTexts(id)' in script
    assert 'function selectTagForEdit(select, editFieldId, oldFieldId)' in script
    assert 'getSelectText(' not in script
    assert 'selectedOptions' in script
