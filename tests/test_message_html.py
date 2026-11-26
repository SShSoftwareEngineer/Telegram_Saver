"""
Tests of the message text to HTML conversion (`message_renderer.py`) and of the escaping of Telegram data on the pages:
every kind of formatting, the escaping of the text and of the link addresses, the checks of the URL schemes, the message
group texts, the status bar and the `<option>` lists. Telethon objects are real, Telegram itself is not used.
Тесты преобразования текста сообщений в HTML (`message_renderer.py`) и экранирования данных Telegram на страницах:
каждый вид форматирования, экранирование текста и адресов ссылок, проверки схем URL, тексты групп сообщений,
строка статуса и списки `<option>`. Объекты Telethon настоящие, сам Telegram не используется.
"""

from datetime import datetime
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from telethon.tl.types import (MessageEntityBlockquote, MessageEntityBold, MessageEntityCode, MessageEntityEmail,
                               MessageEntityHashtag, MessageEntityItalic, MessageEntityMentionName, MessageEntityPre,
                               MessageEntitySpoiler, MessageEntityStrike, MessageEntityTextUrl, MessageEntityUnderline,
                               MessageEntityUrl)
from config import DialogTypes
from database_handler import DatabaseHandler, DbCurrentState, DbDialog, DbMessageGroup, DbMessageSortFilter
from message_renderer import get_safe_url, plain_text_to_html, render_link_html, render_message_html
from telegram_handler import TgFile, TgMessageGroup
from utils import StatusMessages


def span(text: str, part: str) -> tuple[int, int]:
    """Offset and length of `part` in `text` in UTF-16 code units, as Telegram counts them
    Смещение и длина `part` в `text` в кодовых единицах UTF-16, как считает Telegram"""
    index = text.index(part)
    return len(text[:index].encode('utf-16-le')) // 2, len(part.encode('utf-16-le')) // 2


# ----------------------------------------------------------------------------------------------------------------------
# Formatting / Форматирование
# ----------------------------------------------------------------------------------------------------------------------

def test_plain_text_is_escaped_and_line_breaks_become_br():
    """The text is escaped; without entities nothing else is added / Текст экранируется"""
    assert render_message_html('<script>alert("x")</script>\nline & 2', []) == \
        '&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;<br>line &amp; 2'
    assert render_message_html('', None) == '' and render_message_html(None, None) == ''


@pytest.mark.parametrize('entity_class, tag', [
    (MessageEntityBold, 'strong'), (MessageEntityItalic, 'em'), (MessageEntityUnderline, 'u'),
    (MessageEntityStrike, 'del'), (MessageEntityCode, 'code'), (MessageEntityBlockquote, 'blockquote')])
def test_simple_formatting(entity_class, tag: str):
    """Bold, italic, underline, strikethrough, code and quote become one tag around the fragment"""
    text = 'before target after'
    offset, length = span(text, 'target')
    assert render_message_html(text, [entity_class(offset, length)]) == f'before <{tag}>target</{tag}> after'


def test_spoiler_is_hidden_by_css_class():
    """A spoiler gets a class that the CSS hides; the text itself stays escaped / Спойлер - класс, скрываемый CSS"""
    text = 'a <secret> b'
    offset, length = span(text, '<secret>')
    assert render_message_html(text, [MessageEntitySpoiler(offset, length)]) == \
        'a <span class="tg-spoiler">&lt;secret&gt;</span> b'


def test_code_block_keeps_line_breaks_and_escapes():
    """A code block keeps the line breaks (no <br> inside), escapes the code and gets a checked language class"""
    text = 'if a < b:\n    run()'
    assert render_message_html(text, [MessageEntityPre(0, len(text), 'python')]) == \
        '<pre><code class="language-python">if a &lt; b:\n    run()</code></pre>'
    assert render_message_html('x', [MessageEntityPre(0, 1, '')]) == '<pre><code>x</code></pre>'


def test_code_block_language_cannot_break_out_of_the_attribute():
    """A language name with quotes or spaces is not put into the class attribute / Небезопасное имя языка не берется"""
    result = render_message_html('x', [MessageEntityPre(0, 1, 'a" onclick="alert(1)')])
    assert result == '<pre><code>x</code></pre>'


def test_nested_entities_are_nested_tags():
    """Bold with italic inside gives properly nested tags / Вложенные сущности - вложенные теги"""
    text = 'ab cd ef'
    assert render_message_html(text, [MessageEntityItalic(3, 2), MessageEntityBold(0, 8)]) == \
        '<strong>ab <em>cd</em> ef</strong>'


def test_partly_overlapping_entities_stay_well_formed():
    """Overlapping entities (not nested) are closed and opened again, so the tags are never mis-nested"""
    assert render_message_html('abcdef', [MessageEntityBold(0, 4), MessageEntityItalic(2, 4)]) == \
        '<strong>ab<em>cd</em></strong><em>ef</em>'


def test_offsets_are_counted_in_utf16_units():
    """An emoji takes two UTF-16 units: the formatting after it must not shift / Эмодзи - две единицы UTF-16"""
    text = '\U0001F600 bold'
    offset, length = span(text, 'bold')
    assert offset == 3
    assert render_message_html(text, [MessageEntityBold(offset, length)]) == '\U0001F600 <strong>bold</strong>'


def test_unknown_and_out_of_range_entities_are_plain_text():
    """A hashtag (not rendered), an empty and an out-of-range entity change nothing / Неизвестные сущности - текст"""
    text = '#tag text'
    entities = [MessageEntityHashtag(0, 4), MessageEntityBold(5, 0), MessageEntityBold(100, 5)]
    assert render_message_html(text, entities) == '#tag text'


# ----------------------------------------------------------------------------------------------------------------------
# Links / Ссылки
# ----------------------------------------------------------------------------------------------------------------------

def test_text_link():
    """A text link keeps the address (escaped) and opens in a new tab without access to the opener page"""
    text = 'see site'
    offset, length = span(text, 'site')
    result = render_message_html(text, [MessageEntityTextUrl(offset, length, 'https://example.com/?a=1&b=2')])
    assert result == ('see <a href="https://example.com/?a=1&amp;b=2" target="_blank" rel="noopener noreferrer">'
                      'site</a>')


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'java\tscript:alert(1)',
                                 ' javascript:alert(1)', 'data:text/html,<script>alert(1)</script>',
                                 'vbscript:msgbox(1)'])
def test_dangerous_link_schemes_give_no_link(url: str):
    """A link with a dangerous scheme is not created: the text stays, there is no <a> and no address"""
    result = render_message_html('click', [MessageEntityTextUrl(0, 5, url)])
    assert result == 'click'


def test_quotes_in_link_address_are_escaped():
    """A quote in the address cannot close the href attribute / Кавычка в адресе не закрывает атрибут href"""
    result = render_message_html('x', [MessageEntityTextUrl(0, 1, 'https://e.com/" onmouseover="alert(1)')])
    # The space is removed by the address check, the quotes are escaped / Пробел удаляется, кавычки экранируются
    assert 'href="https://e.com/&quot;onmouseover=&quot;alert(1)"' in result
    assert '"onmouseover="' not in result and '" onmouseover="' not in result


def test_url_entity_without_scheme_gets_https():
    """A plain address in the text (a URL entity) becomes a link, an address without a scheme gets https://"""
    text = 'go to example.com now'
    offset, length = span(text, 'example.com')
    assert 'href="https://example.com"' in render_message_html(text, [MessageEntityUrl(offset, length)])


def test_url_entity_with_dangerous_scheme_gives_no_link():
    """The text of a URL entity is checked the same way as an explicit address / Адрес из текста проверяется так же"""
    assert render_message_html('javascript:alert(1)', [MessageEntityUrl(0, 19)]) == 'javascript:alert(1)'


def test_email_and_user_mention_links():
    """An e-mail becomes mailto:, a mention by ID becomes tg://user?id= / e-mail и упоминание по ID"""
    mail = render_message_html('a@b.com', [MessageEntityEmail(0, 7)])
    assert mail.startswith('<a href="mailto:a@b.com"')
    mention = render_message_html('Ann', [MessageEntityMentionName(0, 3, 12345)])
    assert mention.startswith('<a href="tg://user?id=12345"')


@pytest.mark.parametrize('url, expected', [
    ('https://example.com/a', 'https://example.com/a'), ('http://example.com', 'http://example.com'),
    ('tg://resolve?domain=x', 'tg://resolve?domain=x'), ('mailto:a@b.com', 'mailto:a@b.com'),
    ('example.com/path', 'https://example.com/path'), ('example.com:8080/x', 'https://example.com:8080/x'),
    ('javascript:alert(1)', None), ('data:text/html,x', None), ('file:///etc/passwd', None), ('', None),
    (None, None), ('\t \n', None)])
def test_get_safe_url(url, expected):
    """Only http, https, tg and mailto pass; a scheme-less address gets https:// / Пропускаются только разрешенные"""
    assert get_safe_url(url) == expected


def test_plain_text_to_html_and_render_link_html():
    """Helpers for the descriptions of web page previews / Вспомогательные функции для описаний превью страниц"""
    assert plain_text_to_html('a < b\nc') == 'a &lt; b<br>c' and plain_text_to_html(None) == ''
    assert render_link_html('https://e.com/?a=1&b=2', 'https://e.com/?a=1&b=2') == (
        '<a href="https://e.com/?a=1&amp;b=2" target="_blank" rel="noopener noreferrer">https://e.com/?a=1&amp;b=2</a>')
    assert render_link_html('javascript:alert(1)', '<b>x</b>') == '&lt;b&gt;x&lt;/b&gt;'


# ----------------------------------------------------------------------------------------------------------------------
# Message group / Группа сообщений
# ----------------------------------------------------------------------------------------------------------------------

def make_message(message_id: int, text: str, entities=None) -> SimpleNamespace:
    """Fake Telethon message with the attributes `add_message` uses / Заглушка сообщения Telethon"""
    return SimpleNamespace(id=message_id, sender_id=1, raw_text=text, entities=entities,
                           date=datetime(2026, 1, 2, 3, 4, message_id))


def test_group_texts_are_joined_as_html_and_as_plain_text():
    """The texts of the group are joined by an empty line in both forms; the HTML is escaped, the plain text is not"""
    group = TgMessageGroup('42_1', 42)
    group.add_message(make_message(1, 'one <b>', [MessageEntityBold(0, 3)]))  # type: ignore[arg-type]
    group.add_message(make_message(2, 'two\nlines'))  # type: ignore[arg-type]
    assert group.html == '<strong>one</strong> &lt;b&gt;<br><br>two<br>lines'
    assert group.plain_text == 'one <b>\n\ntwo\nlines'


def test_group_without_text_has_empty_texts():
    """A message without text (only media) adds nothing / Сообщение без текста (только медиа) ничего не добавляет"""
    group = TgMessageGroup('42_2', 42)
    group.add_message(make_message(1, ''))  # type: ignore[arg-type]
    assert (group.html, group.plain_text) == ('', '')


def test_web_page_description_is_added_safely():
    """The description of a web page preview: the link and the text in both forms, escaped / Описание превью страницы"""
    group = TgMessageGroup('42_3', 42)
    group.add_message(make_message(1, 'look'))  # type: ignore[arg-type]
    tg_file = TgFile(42, '42_3', None, 1, 'https://e.com/?a=1&b=2\n\n<i>page</i>', '', '', '', 0,  # type: ignore[arg-type]
                     description_html='<a href="https://e.com/?a=1&amp;b=2">x</a><br><br>&lt;i&gt;page&lt;/i&gt;')
    group.add_message_file(tg_file)
    assert group.plain_text == 'look\n\nhttps://e.com/?a=1&b=2\n\n<i>page</i>'
    assert group.html == 'look<br><br><a href="https://e.com/?a=1&amp;b=2">x</a><br><br>&lt;i&gt;page&lt;/i&gt;'


def test_truncated_text_is_cut_from_plain_text_without_tags():
    """The preview is cut from the plain text, so no tag can be cut in half and no markup gets into it"""
    group = TgMessageGroup('42_4', 42)
    link_text = 'link'
    group.add_message(make_message(1, f'{link_text} ' + 'word ' * 100,  # type: ignore[arg-type]
                                   [MessageEntityTextUrl(0, 4, 'https://example.com/' + 'a' * 300)]))
    group.set_truncated_text()
    assert group.truncated_text.startswith('link word')
    assert group.truncated_text.endswith('...')
    assert '<' not in group.truncated_text and 'http' not in group.truncated_text


# ----------------------------------------------------------------------------------------------------------------------
# Escaping on the pages / Экранирование на страницах
# ----------------------------------------------------------------------------------------------------------------------

EVIL_TITLE = '<script>alert("title")</script>'
EVIL_TEXT = '<img src=x onerror=alert("text")>'


def test_status_messages_are_escaped_once_and_kept_raw_in_the_list():
    """The status bar HTML escapes the operation and the reports; `report_list` keeps the original text"""
    status = StatusMessages()
    status.mess_update('Chat <b>x</b>', 'file "<i>a</i>" & more', True)
    assert '&lt;b&gt;x&lt;/b&gt;' in status.messages['sb_operation']
    assert '&quot;&lt;i&gt;a&lt;/i&gt;&quot; &amp; more' in status.messages['sb_report']
    assert '<b>' not in status.messages['sb_operation'] and '<i>' not in status.messages['sb_report']
    assert '<i>a</i>' in status.report_list[0]  # type: ignore[index]


def test_option_list_escapes_values():
    """A dialog title or a tag name with markup cannot break out of the <option> / Названия в <option> экранируются"""
    items = [SimpleNamespace(id='1" onclick="x', name=EVIL_TITLE)]
    result = DatabaseHandler.get_select_content_string(items, 'id', 'name')
    assert '<script>' not in result and '&lt;script&gt;' in result
    assert 'value="1&quot; onclick=&quot;x"' in result


def test_database_pages_escape_titles_and_previews_but_output_stored_html(client: TestClient,
                                                                         db_handler: DatabaseHandler):
    """The list and the details of the database tab: the dialog title and the plain text preview are escaped by the
    template, the stored message HTML is output as it is / Заголовок и фрагмент текста экранируются, HTML выводится"""
    db_handler.message_sort_filter = DbMessageSortFilter()
    db_handler.current_state = DbCurrentState()
    session = db_handler.session
    session.add(DbDialog(dialog_id=1, title=EVIL_TITLE, dialog_type_id=DialogTypes.CHANNEL.value))
    group = DbMessageGroup(grouped_id='1_1', date=datetime(2026, 1, 1, 3, 4, 5), html='<strong>ok</strong> &lt;img&gt;',
                           plain_text=EVIL_TEXT, truncated_text=EVIL_TEXT, sender_id=7, dialog_id=1)
    session.add(group)
    session.commit()
    db_handler.current_state.message_group_list = [group]

    page = client.get('/').text
    message_list = page.split('id="db_messages"')[1].split('id="db_details"')[0]
    assert '<script>' not in message_list and '&lt;script&gt;' in message_list
    assert '<img src=x' not in message_list and '&lt;img src=x onerror=alert(&#34;text&#34;)&gt;' in message_list

    details = client.get('/db_details/1_1').ui()['db_details']
    assert '<script>' not in details and '&lt;script&gt;' in details
    assert '<strong>ok</strong> &lt;img&gt;' in details


# ----------------------------------------------------------------------------------------------------------------------
# Search by message text / Поиск по тексту сообщений
# ----------------------------------------------------------------------------------------------------------------------

def search(db_handler: DatabaseHandler, query: str) -> list[str]:
    """IDs of the saved groups found by the text filter / ID сохраненных групп, найденных фильтром по тексту"""
    db_handler.message_sort_filter = DbMessageSortFilter()
    db_handler.message_sort_filter.message_query = query
    return sorted(group.grouped_id for group in db_handler.get_message_group_list())


def test_search_uses_plain_text_not_markup(db_handler: DatabaseHandler):
    """A query that matches only the HTML markup (a tag, an attribute) finds nothing; the visible text is found"""
    session = db_handler.session
    session.add(DbDialog(dialog_id=1, title='Chat', dialog_type_id=DialogTypes.CHANNEL.value))
    session.add(DbMessageGroup(grouped_id='1_1', date=datetime(2026, 1, 1), plain_text='see the site',
                               html='see the <a href="https://e.com" target="_blank">site</a>', truncated_text='',
                               sender_id=7, dialog_id=1))
    session.commit()
    assert search(db_handler, 'href') == [] and search(db_handler, 'target') == [] and search(db_handler, '<a') == []
    assert search(db_handler, 'the site') == ['1_1']


def test_search_treats_percent_and_underscore_literally(db_handler: DatabaseHandler):
    """`%` and `_` in a query are ordinary characters, not LIKE wildcards / `%` и `_` - обычные символы"""
    session = db_handler.session
    session.add(DbDialog(dialog_id=1, title='Chat', dialog_type_id=DialogTypes.CHANNEL.value))
    for number, text in enumerate(['discount 50% today', 'snake_case name', 'plain words', r'back\slash'], start=1):
        session.add(DbMessageGroup(grouped_id=f'1_{number}', date=datetime(2026, 1, number), plain_text=text,
                                   html=text, truncated_text='', sender_id=7, dialog_id=1))
    session.commit()
    assert search(db_handler, '%') == ['1_1']
    assert search(db_handler, '_') == ['1_2']
    assert search(db_handler, 'e_c') == ['1_2']  # `_` is not "any one character" / `_` - не "любой символ"
    assert search(db_handler, '50%') == ['1_1']
    assert search(db_handler, chr(92)) == ['1_4']  # a backslash is an ordinary character too / обратная косая - тоже


def test_search_ignores_case_of_cyrillic_text(db_handler: DatabaseHandler):
    """The SQLite `lower()` knows only ASCII; the search must not depend on the case of Cyrillic letters either"""
    session = db_handler.session
    session.add(DbDialog(dialog_id=1, title='Chat', dialog_type_id=DialogTypes.CHANNEL.value))
    for number, text in enumerate(['Привіт, Світ', 'Hello World', 'без збігів'], start=1):
        session.add(DbMessageGroup(grouped_id=f'1_{number}', date=datetime(2026, 1, number), plain_text=text,
                                   html=text, truncated_text='', sender_id=7, dialog_id=1))
    session.commit()
    assert search(db_handler, 'привіт') == ['1_1'] and search(db_handler, 'СВІТ') == ['1_1']
    assert search(db_handler, 'world') == ['1_2'] and search(db_handler, 'WORLD') == ['1_2']
