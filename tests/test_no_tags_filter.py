"""
Tests of the special "(No tags)" item of the tag filter (F3): the name is a constant; the item is the first option of
the list of all tags (ID 0, bold, whatever the sorting is); in the filter it adds the messages without tags to the result
of the other keywords (or is the whole result when it is alone); it is not a tag, so it cannot be added, removed or
renamed. The database is real (a temporary SQLite file).
Тесты особого пункта «(No tags)» фильтра тегов (F3): имя - константа; пункт - первый в списке всех тегов (ID 0, жирный,
при любой сортировке); в фильтре он добавляет к результату остальных слов сообщения без тегов (или сам является всем
результатом, если он один); это не тег, поэтому его нельзя добавить, удалить или переименовать. База данных настоящая
(временный файл SQLite).
"""

import pytest
from fastapi.testclient import TestClient
from config import FormCfg, GlobalConst
from database_handler import DatabaseHandler, DbCurrentState, DbMessageSortFilter, is_no_tags_name
from utils import status_messages
from test_tag_methods import add_group, all_tags, group_tags

NO_TAGS = GlobalConst.no_tags_name
ALL_TAGS = FormCfg.db_detail_tags['all_detail_tags']
EDIT_NAME = FormCfg.db_detail_tags['edit_tag_name']
OLD_NAME = FormCfg.db_detail_tags['old_tag_name']
CHECKBOX = FormCfg.db_checkbox_list['db_checkbox_list']
SORTING = FormCfg.db_detail_tags['tag_sorting_field']


@pytest.fixture(name='groups')
def groups_fixture(db_handler: DatabaseHandler) -> dict[str, str]:
    """The groups: with `alpha`+`beta`, with `beta`, and two without tags; the filter is clean"""
    db_handler.current_state = DbCurrentState()
    ids = {'ab': add_group(db_handler, 1, ('alpha', 'beta')), 'b': add_group(db_handler, 2, ('beta',)),
           'none1': add_group(db_handler, 3), 'none2': add_group(db_handler, 4)}
    db_handler.message_sort_filter = DbMessageSortFilter()
    return ids


def found(db_handler: DatabaseHandler, query: str, mode: str | None = None) -> set[str]:
    """IDs of the groups found by the tag filter / ID групп, найденных фильтром тегов"""
    db_handler.message_sort_filter = DbMessageSortFilter()
    db_handler.message_sort_filter.tag_query = query  # type: ignore[assignment]
    db_handler.message_sort_filter.tag_match_all = mode  # type: ignore[assignment]
    return {group.grouped_id for group in db_handler.get_message_group_list()}


# ----------------------------------------------------------------------------------------------------------------------
# The filter / Фильтр
# ----------------------------------------------------------------------------------------------------------------------

def test_alone_it_finds_only_the_untagged(db_handler: DatabaseHandler, groups: dict[str, str]):
    """`(No tags)` alone is the messages without tags (the mode does not matter)"""
    expected = {groups['none1'], groups['none2']}
    assert found(db_handler, NO_TAGS) == expected
    assert found(db_handler, NO_TAGS, '1') == expected
    assert found(db_handler, f' {NO_TAGS.upper()} ; ') == expected  # spaces and case do not matter


@pytest.mark.parametrize('mode', [None, '0', '1'])
def test_with_a_tag_it_adds_the_untagged(db_handler: DatabaseHandler, groups: dict[str, str], mode: str | None):
    """With a keyword the result of the keyword is joined with the untagged, in OR and in AND mode"""
    assert found(db_handler, f'alpha; {NO_TAGS}', mode) == {groups['ab'], groups['none1'], groups['none2']}


def test_other_keywords_keep_their_logic(db_handler: DatabaseHandler, groups: dict[str, str]):
    """Without it OR and AND work as before; with it the AND result of the keywords is joined with the untagged"""
    assert found(db_handler, 'alpha; beta', '1') == {groups['ab']}
    assert found(db_handler, 'alpha; beta', '0') == {groups['ab'], groups['b']}
    assert found(db_handler, f'alpha; beta; {NO_TAGS}', '1') == {groups['ab'], groups['none1'], groups['none2']}
    assert found(db_handler, f'alpha; beta; {NO_TAGS}', '0') == {groups['ab'], groups['b'], groups['none1'],
                                                                groups['none2']}


def test_it_is_not_searched_in_the_tag_names(db_handler: DatabaseHandler, groups: dict[str, str]):
    """A tag that only contains the text is not found by it: the whole keyword is the special item"""
    tricky = add_group(db_handler, 5, (f'my {NO_TAGS} tag',))
    assert tricky not in found(db_handler, NO_TAGS)
    assert found(db_handler, f'{NO_TAGS} tag') == {tricky}  # a different keyword is searched as usual


def test_it_combines_with_the_other_filters(db_handler: DatabaseHandler, groups: dict[str, str]):
    """The date filter works together with it: only the untagged messages of the period"""
    db_handler.message_sort_filter = DbMessageSortFilter()
    db_handler.message_sort_filter.tag_query = NO_TAGS  # type: ignore[assignment]
    db_handler.message_sort_filter.date_from = '2026-01-04'  # type: ignore[assignment]
    assert {group.grouped_id for group in db_handler.get_message_group_list()} == {groups['none2']}


def test_filter_route(client: TestClient, db_handler: DatabaseHandler, groups: dict[str, str]):
    """The same through the route: the counter of the list has the two untagged messages"""
    form = {FormCfg.db_message_filter['tag_query']: NO_TAGS, FormCfg.db_message_filter['sorting_field']: '0',
            FormCfg.db_message_filter['sorting_order']: '0'}
    response = client.post('/db_message_apply_filters', data=form)
    assert response.status_code == 200 and response.ui()['db-messages-count'] == '(2)'


# ----------------------------------------------------------------------------------------------------------------------
# The list of all tags / Список всех тегов
# ----------------------------------------------------------------------------------------------------------------------

def test_name_check():
    """The name is compared ignoring spaces around and the case"""
    assert is_no_tags_name(NO_TAGS) and is_no_tags_name(f'  {NO_TAGS.upper()} ')
    assert not is_no_tags_name('No tags') and not is_no_tags_name(f'{NO_TAGS} 2')


def test_select_has_the_item_first(db_handler: DatabaseHandler, groups: dict[str, str]):
    """The item is the first option (ID 0, bold class), then the tags; with no tags at all it is the only one"""
    db_handler.all_tags_list = db_handler.get_all_tag_list()
    options = db_handler.get_all_tags_select().split('\n')
    assert options[0].startswith(f'<option value="{GlobalConst.no_tags_id}" class="no-tags-option"')
    assert options[0].endswith(f'>{NO_TAGS}</option>')
    assert len(options) == 3  # the item, alpha, beta
    db_handler.all_tags_list = []
    assert db_handler.get_all_tags_select().count('<option') == 1


@pytest.mark.parametrize('sorting', ['0', '1', '2'])
def test_item_stays_first_whatever_the_sorting(client: TestClient, db_handler: DatabaseHandler,
                                               groups: dict[str, str], sorting: str):
    """The sorting route returns the item as the first option for every sorting"""
    response = client.post('/db_tag_all_sorting', data={SORTING: sorting})
    assert response.status_code == 200
    assert response.ui()[ALL_TAGS].startswith(f'<option value="{GlobalConst.no_tags_id}"')


def test_page_has_the_item(client: TestClient, groups: dict[str, str]):
    """The page of the tab has the item in the list of all tags"""
    assert 'class="no-tags-option"' in client.get('/').text


def test_item_is_not_stored(db_handler: DatabaseHandler, groups: dict[str, str]):
    """The item is not a tag of the database: the database has only the real tags"""
    assert set(all_tags(db_handler)) == {'alpha', 'beta'}


# ----------------------------------------------------------------------------------------------------------------------
# The name is reserved / Имя зарезервировано
# ----------------------------------------------------------------------------------------------------------------------

def box(grouped_id: str) -> str:
    """The value of the checkbox of a message group / Значение чек-бокса группы сообщений"""
    return f'{GlobalConst.select_in_database} {grouped_id}'


@pytest.mark.parametrize('route', ['/db_tag_add', '/db_tag_remove'])
def test_cannot_add_or_remove_it(client: TestClient, db_handler: DatabaseHandler, groups: dict[str, str], route: str):
    """Adding (or removing) a tag with the name does nothing: no tag is created, the status bar explains"""
    status_messages.report_list = []
    response = client.post(route, data={CHECKBOX: [box(groups['none1'])], EDIT_NAME: NO_TAGS})
    assert response.status_code == 200
    assert response.ui() == {}
    assert group_tags(db_handler, groups['none1']) == [] and set(all_tags(db_handler)) == {'alpha', 'beta'}
    assert any('reserved' in report for report in status_messages.report_list or [])


@pytest.mark.parametrize('route', ['/db_tag_update', '/db_tag_update_everywhere'])
def test_cannot_rename_to_or_from_it(client: TestClient, db_handler: DatabaseHandler, groups: dict[str, str],
                                     route: str):
    """A tag is not renamed to the name, and the item is not renamed to another name"""
    form = {CHECKBOX: [box(groups['ab'])]}
    for old, new in (('alpha', NO_TAGS), (NO_TAGS, 'gamma')):
        response = client.post(route, data={**form, OLD_NAME: old, EDIT_NAME: new})
        assert response.status_code == 200
        assert group_tags(db_handler, groups['ab']) == ['alpha', 'beta']
    assert set(all_tags(db_handler)) == {'alpha', 'beta'}


def test_script_does_not_fill_the_fields_from_the_item():
    """The script of the page does not fill the tag name fields when the item is selected (it only goes to the filter)"""
    from pathlib import Path
    script = (Path(__file__).resolve().parent.parent / 'static' / 'js' / 'my_scripts.js').read_text(encoding='utf-8')
    body = script[script.index('function selectTagForEdit('):]
    body = body[:body.index('\n}\n')]
    assert 'no-tags-option' in body
