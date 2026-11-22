"""
Tests of the filter by tags on the database tab: the keywords are the parts between `;` (an empty part must not match
every tag), a keyword matches a part of a tag without regard to case (Cyrillic too), `%`, `_` and `\\` are ordinary
characters.
Тесты фильтра по тегам вкладки БД: ключевые слова - части между `;` (пустая часть не должна совпадать с любым тегом),
слово совпадает с частью тега без учета регистра (кириллица тоже), `%`, `_` и `\\` - обычные символы.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from configs.config import DialogTypes, FormCfg
from database_handler import DatabaseHandler, DbCurrentState, DbDialog, DbMessageGroup, DbMessageSortFilter, DbTag

FILTER_CFG = FormCfg.db_message_filter

# Tags of the groups; the group `g3` has no tags / Теги групп; у группы `g3` тегов нет
TAGS_BY_GROUP = {'g1': ('alpha', 'beta'), 'g2': ('beta',), 'g3': (), 'g4': ('Звіт',), 'g5': ('discount 50%',),
                 'g6': ('snake_case',), 'g7': ('back\\slash',), 'g8': ('art ad',), 'g9': ('abc',)}
ALL_GROUPS = sorted(TAGS_BY_GROUP)


@pytest.fixture
def tagged(db_handler: DatabaseHandler) -> DatabaseHandler:
    """The database with the groups from `TAGS_BY_GROUP` (the same name is the same tag) and a clean filter"""
    session = db_handler.session
    session.add(DbDialog(dialog_id=1, title='Chat', dialog_type_id=DialogTypes.CHANNEL.value))
    tags: dict[str, DbTag] = {}
    for grouped_id, names in TAGS_BY_GROUP.items():
        group = DbMessageGroup(grouped_id=grouped_id, date=datetime(2026, 1, 1, tzinfo=timezone.utc), html='text',
                               plain_text='text', truncated_text='text', sender_id=7, dialog_id=1)
        for name in names:
            group.tags.append(tags.setdefault(name, DbTag(name=name)))
        session.add(group)
    session.commit()
    db_handler.message_sort_filter = DbMessageSortFilter()
    db_handler.current_state = DbCurrentState()
    return db_handler


def by_tags(db_handler: DatabaseHandler, query: str | None, mode: str | None = None) -> list[str]:
    """IDs of the groups found by the tag filter (the query is the text of the form field, the mode is the value of
    its radio buttons: '1' - AND, otherwise OR)"""
    db_handler.message_sort_filter = DbMessageSortFilter()
    db_handler.message_sort_filter.tag_query = query  # type: ignore[assignment]
    db_handler.message_sort_filter.tag_match_all = mode  # type: ignore[assignment]
    return sorted(group.grouped_id for group in db_handler.get_message_group_list())


# ----------------------------------------------------------------------------------------------------------------------
# Parsing of the field / Разбор поля
# ----------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('value, expected', [
    ('alpha', ['alpha']),
    ('alpha;beta', ['alpha', 'beta']),
    (' alpha ; beta ', ['alpha', 'beta']),  # the edges are trimmed / края обрезаются
    ('alpha; ', ['alpha']),                 # the empty part was `%%`: it matched every tag / пустая часть была `%%`
    (';alpha;;', ['alpha']),
    ('art ad', ['art ad']),                 # a space inside is a part of the keyword / пробел внутри - часть слова
    ('art  ad; x', ['art  ad', 'x']),       # inner spaces are kept as they are / внутренние пробелы не меняются
    ('', None), ('   ', None), (';', None), (' ; ; ', None), (None, None),  # no keywords: the filter is off
])
def test_keywords_of_the_field(value: str | None, expected: list[str] | None):
    """The keywords are the non-empty parts between the separators; no keywords means no filter"""
    message_filter = DbMessageSortFilter()
    message_filter.tag_query = value  # type: ignore[assignment]
    assert message_filter.tag_query == expected


# ----------------------------------------------------------------------------------------------------------------------
# Search / Поиск
# ----------------------------------------------------------------------------------------------------------------------

def test_empty_part_does_not_match_every_tag(tagged: DatabaseHandler):
    """`alpha; ` finds only the group with `alpha` (the empty part used to make the filter find all tagged groups)"""
    assert by_tags(tagged, 'alpha; ') == ['g1']
    assert by_tags(tagged, ';alpha') == ['g1']


@pytest.mark.parametrize('query', ['', '   ', ';', ' ; ; ', None])
def test_no_keywords_means_no_filter(tagged: DatabaseHandler, query: str | None):
    """Without keywords the filter is off: every group is found, those without tags too"""
    assert by_tags(tagged, query) == ALL_GROUPS


def test_part_of_a_tag_without_regard_to_case(tagged: DatabaseHandler):
    """A keyword matches a part of a tag, the case does not matter (Cyrillic too: SQLite `lower()` is ASCII only)"""
    assert by_tags(tagged, 'beta') == ['g1', 'g2']
    assert by_tags(tagged, 'alph') == ['g1'] and by_tags(tagged, 'ALPHA') == ['g1']
    assert by_tags(tagged, 'зві') == ['g4'] and by_tags(tagged, 'ЗВІ') == ['g4']


def test_a_keyword_with_a_space_is_one_phrase(tagged: DatabaseHandler):
    """`art ad` is searched as one phrase, not as two words; two words need the separator"""
    assert by_tags(tagged, 'art ad') == ['g8']
    assert by_tags(tagged, 'art') == ['g8'] and by_tags(tagged, 'ad') == ['g8']
    assert by_tags(tagged, 'ad art') == []


def test_groups_without_tags_never_match(tagged: DatabaseHandler):
    """A group without tags is found only when the filter is off / Группа без тегов находится, только без фильтра"""
    assert 'g3' not in by_tags(tagged, 'a') and by_tags(tagged, 'no such tag') == []


def test_special_characters_are_ordinary(tagged: DatabaseHandler):
    """`%`, `_` and a backslash are not LIKE wildcards: they are searched literally"""
    assert by_tags(tagged, '%') == ['g5'] and by_tags(tagged, '50%') == ['g5']
    assert by_tags(tagged, '_') == ['g6']
    assert by_tags(tagged, 'a_c') == []  # `_` is not "any one character": it would find `abc` / `_` - не любой символ
    assert by_tags(tagged, chr(92)) == ['g7']


def test_filter_route_ignores_the_empty_part(client: TestClient, tagged: DatabaseHandler):
    """The same through the route: the counter of the list has only the group with the tag"""
    form = {FILTER_CFG['tag_query']: 'alpha; ', FILTER_CFG['sorting_field']: '0', FILTER_CFG['sorting_order']: '0'}
    response = client.post('/db_message_apply_filters', data=form)
    assert response.status_code == 200
    assert response.json()['db-messages-count'] == '(1)'


# ----------------------------------------------------------------------------------------------------------------------
# OR / AND mode / Режим ИЛИ / И
# ----------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('value, expected', [('1', True), ('0', False), ('', False), ('x', False), (None, False)])
def test_mode_of_the_field(value: str | None, expected: bool):
    """Only '1' switches AND on; the default and any other value (also a missing field) is OR"""
    message_filter = DbMessageSortFilter()
    assert message_filter.tag_match_all is False
    message_filter.tag_match_all = value  # type: ignore[assignment]
    assert message_filter.tag_match_all is expected


def test_or_mode_finds_any_keyword(tagged: DatabaseHandler):
    """OR (the default): a message with at least one of the keywords is found"""
    assert by_tags(tagged, 'alpha; beta') == ['g1', 'g2']
    assert by_tags(tagged, 'alpha; beta', '0') == ['g1', 'g2']
    assert by_tags(tagged, 'alpha; zzz') == ['g1']


def test_and_mode_needs_every_keyword(tagged: DatabaseHandler):
    """AND: only the message that has all the keywords is found (`g2` has `beta`, but not `alpha`)"""
    assert by_tags(tagged, 'alpha; beta', '1') == ['g1']
    assert by_tags(tagged, 'beta; alpha', '1') == ['g1']  # the order does not matter / порядок не важен
    assert by_tags(tagged, 'alpha; zzz', '1') == []       # one keyword matches nothing: nothing is found
    assert by_tags(tagged, 'beta; Звіт', '1') == []       # no message has both / нет сообщения с обоими


def test_and_mode_with_parts_case_and_empty_parts(tagged: DatabaseHandler):
    """AND works with parts of tags, any case and ignores the empty parts, like OR"""
    assert by_tags(tagged, 'alp; bet', '1') == ['g1']
    assert by_tags(tagged, 'ALPHA; BETA', '1') == ['g1']
    assert by_tags(tagged, 'alpha; ; beta; ', '1') == ['g1']


def test_and_mode_one_tag_may_match_several_keywords(tagged: DatabaseHandler):
    """Every keyword must match some tag of the message, not a different one: one tag can match both keywords"""
    assert by_tags(tagged, 'alpha; alp', '1') == ['g1']
    assert by_tags(tagged, 'art; ad', '1') == ['g8']


def test_modes_agree_for_one_keyword_and_no_keywords(tagged: DatabaseHandler):
    """One keyword gives the same result in both modes; without keywords the filter is off in both"""
    for mode in ('0', '1'):
        assert by_tags(tagged, 'beta', mode) == ['g1', 'g2']
        assert by_tags(tagged, ' ; ', mode) == ALL_GROUPS


def test_filter_route_passes_the_mode(client: TestClient, tagged: DatabaseHandler):
    """The same through the route: the radio value goes to the filter; a missing value is OR"""
    form = {FILTER_CFG['tag_query']: 'alpha; beta', FILTER_CFG['sorting_field']: '0',
            FILTER_CFG['sorting_order']: '0'}
    counts = {}
    for mode in ('1', '0', None):
        data = dict(form)
        if mode is not None:
            data[FILTER_CFG['tag_mode']] = mode
        response = client.post('/db_message_apply_filters', data=data)
        assert response.status_code == 200
        counts[mode] = response.json()['db-messages-count']
    assert counts == {'1': '(1)', '0': '(2)', None: '(2)'}


def test_page_has_the_mode_radio_buttons(client: TestClient):
    """The main page has the OR / AND radio buttons under the tag field; OR is checked by default"""
    page = client.get('/').text
    mode_name = FILTER_CFG['tag_mode']
    assert f'id="{mode_name}"' in page  # the container the page script reads the value from / контейнер для скрипта
    assert f'name="{mode_name}" value="0" checked' in page
    assert f'name="{mode_name}" value="1">' in page
