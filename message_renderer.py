"""
Safe conversion of Telegram message text with entities to HTML.
Безопасное преобразование текста сообщений Telegram с сущностями (entities) в HTML.

The HTML is built here, not cleaned afterwards: every piece of text goes through `html.escape`, the tags come
from a fixed table, and a link is created only for an allowed URL scheme. So the result is safe to output with
`|safe` in the templates. An entity of an unknown type is output as plain escaped text.
HTML строится здесь, а не очищается потом: каждый фрагмент текста проходит через `html.escape`, теги берутся из
фиксированной таблицы, а ссылка создается только для разрешенной схемы URL. Поэтому результат безопасно выводить
в шаблонах через `|safe`. Сущность неизвестного типа выводится как обычный экранированный текст.

render_message_html: a function converting the raw text and entities of a message to HTML
plain_text_to_html: a function converting plain text to HTML (escaping, line breaks)
render_link_html: a function creating an HTML link with a check of the URL scheme
get_safe_url: a function returning a URL with an allowed scheme, or None
"""

import re
from dataclasses import dataclass
from html import escape
from typing import Sequence

from telethon.tl.types import (MessageEntityBlockquote, MessageEntityBold, MessageEntityCode, MessageEntityEmail,
                               MessageEntityItalic, MessageEntityMentionName, MessageEntityPre,
                               MessageEntitySpoiler, MessageEntityStrike, MessageEntityTextUrl, MessageEntityUnderline,
                               MessageEntityUrl, TypeMessageEntity)

# URL schemes allowed in links / Схемы URL, разрешенные в ссылках
ALLOWED_URL_SCHEMES = ('http', 'https', 'tg', 'mailto')
# Control characters and spaces: browsers ignore them inside a scheme ("java\tscript:"), so they are removed
# Управляющие символы и пробелы: браузеры игнорируют их внутри схемы ("java\tscript:"), поэтому их удаляем
_CONTROL_CHARS = re.compile(r'[\x00-\x20\x7f-\x9f]')
_URL_SCHEME = re.compile(r'^([a-zA-Z][a-zA-Z0-9+.\-]*):')
# "example.com:8080/path" looks like a scheme "example.com", but after the colon there is a port
# "example.com:8080/path" похоже на схему "example.com", но после двоеточия стоит порт
_PORT_AFTER_COLON = re.compile(r'^[^:]*:\d+(/|\?|#|$)')
# Programming language name of a code block: only safe characters go to the class attribute
# Название языка блока кода: в атрибут class попадают только безопасные символы
_LANGUAGE_NAME = re.compile(r'^[\w+#.\-]{1,30}$')

_LINK_ATTRIBUTES = 'target="_blank" rel="noopener noreferrer"'
# Entities that are one plain tag around the fragment / Сущности, которые - один простой тег вокруг фрагмента
_SIMPLE_TAGS = ((MessageEntityBold, 'strong'), (MessageEntityItalic, 'em'), (MessageEntityUnderline, 'u'),
                (MessageEntityStrike, 'del'), (MessageEntityCode, 'code'), (MessageEntityBlockquote, 'blockquote'))


@dataclass
class _OpenTag:
    """
    A rendered entity: its range in UTF-16 code units and its tags
    Отрисованная сущность: ее диапазон в кодовых единицах UTF-16 и ее теги
    """

    start: int
    end: int
    open_tag: str
    close_tag: str
    is_pre: bool = False


def get_safe_url(url: str | None) -> str | None:
    """
    Returns a URL with an allowed scheme (http, https, tg, mailto), or None for any other scheme (javascript:, data:)
    Возвращает URL с разрешенной схемой (http, https, tg, mailto), либо None для любой другой схемы (javascript:, data:)
    Attributes:
        url (str | None): URL from a message
    Returns:
        str | None: the URL without control characters, or None if it is not allowed
    """

    if not url:
        return None
    cleaned_url = _CONTROL_CHARS.sub('', url)
    if not cleaned_url:
        return None
    scheme_match = _URL_SCHEME.match(cleaned_url)
    if scheme_match and not _PORT_AFTER_COLON.match(cleaned_url):
        return cleaned_url if scheme_match.group(1).lower() in ALLOWED_URL_SCHEMES else None
    # No scheme (for example "example.com"): Telegram opens such a link as a web address
    # Схемы нет (например "example.com"): Telegram открывает такую ссылку как веб-адрес
    return cleaned_url if cleaned_url.startswith(('http://', 'https://')) else f'https://{cleaned_url}'


def plain_text_to_html(text: str | None) -> str:
    """
    Converts plain text to HTML: escapes the text and replaces line breaks with <br>
    Преобразует обычный текст в HTML: экранирует текст и заменяет переводы строк на <br>
    Attributes:
        text (str | None): plain text
    Returns:
        str: HTML
    """

    return escape(text).replace('\n', '<br>') if text else ''


def render_link_html(url: str | None, label: str | None) -> str:
    """
    Creates an HTML link; if the URL scheme is not allowed, returns only the escaped label
    Создает HTML ссылку; если схема URL не разрешена, возвращает только экранированную подпись
    Attributes:
        url (str | None): link address
        label (str | None): link text
    Returns:
        str: HTML of the link
    """

    safe_url = get_safe_url(url)
    if safe_url is None:
        return escape(label or '')
    return f'<a href="{escape(safe_url)}" {_LINK_ATTRIBUTES}>{escape(label or '')}</a>'


def _get_link_url(entity: TypeMessageEntity, entity_text: str) -> str | None:
    """
    Returns the address of a link entity (not yet checked), or None if the entity is not a link
    Возвращает адрес сущности-ссылки (еще не проверенный), либо None, если сущность не ссылка
    Attributes:
        entity (TypeMessageEntity): Telethon message entity
        entity_text (str): the part of the message text covered by the entity
    Returns:
        str | None: link address
    """

    if isinstance(entity, MessageEntityTextUrl):
        return entity.url
    if isinstance(entity, MessageEntityUrl):
        return entity_text
    if isinstance(entity, MessageEntityEmail):
        return f'mailto:{entity_text}'
    if isinstance(entity, MessageEntityMentionName):
        return f'tg://user?id={int(entity.user_id)}'
    return None


def _get_entity_tags(entity: TypeMessageEntity, entity_text: str) -> tuple[str, str] | None:
    """
    Returns the opening and closing tags for an entity, or None if the entity is not rendered
    Возвращает открывающий и закрывающий теги для сущности, либо None, если сущность не отображается
    Attributes:
        entity (TypeMessageEntity): Telethon message entity
        entity_text (str): the part of the message text covered by the entity
    Returns:
        tuple[str, str] | None: opening and closing tags
    """

    for entity_type, tag in _SIMPLE_TAGS:
        if isinstance(entity, entity_type):
            return f'<{tag}>', f'</{tag}>'
    if isinstance(entity, MessageEntitySpoiler):
        return '<span class="tg-spoiler">', '</span>'
    if isinstance(entity, MessageEntityPre):
        language = getattr(entity, 'language', '') or ''
        code_open = f'<code class="language-{language}">' if _LANGUAGE_NAME.match(language) else '<code>'
        return f'<pre>{code_open}', '</code></pre>'
    # Links: the address is checked and escaped / Ссылки: адрес проверяется и экранируется
    safe_url = get_safe_url(_get_link_url(entity, entity_text))
    if safe_url is None:
        return None
    return f'<a href="{escape(safe_url)}" {_LINK_ATTRIBUTES}>', '</a>'


def _collect_tags(units: bytes, entities: Sequence[TypeMessageEntity] | None) -> list[_OpenTag]:
    """
    Builds the list of rendered entities, outer ones first; entities that are empty, out of range or not rendered
    are skipped
    Строит список отображаемых сущностей, внешние первыми; пустые, выходящие за текст и не отображаемые сущности
    пропускаются
    Attributes:
        units (bytes): the message text in UTF-16 (little endian)
        entities (Sequence[TypeMessageEntity] | None): message entities
    Returns:
        list[_OpenTag]: entities with their tags
    """

    total_length = len(units) // 2
    tags: list[_OpenTag] = []
    for entity in entities or []:
        start = max(0, entity.offset)
        end = min(total_length, entity.offset + entity.length)
        if end <= start:
            continue
        entity_tags = _get_entity_tags(entity, units[2 * start:2 * end].decode('utf-16-le', errors='replace'))
        if entity_tags:
            tags.append(_OpenTag(start, end, entity_tags[0], entity_tags[1], isinstance(entity, MessageEntityPre)))
    # Outer entities open first: earlier start, then longer / Внешние сущности открываются первыми
    tags.sort(key=lambda tag: (tag.start, -tag.end))
    return tags


def _close_ended_tags(stack: list[_OpenTag], boundary: int, result: list[str]) -> None:
    """
    Closes the entities that end at the boundary. An entity above them on the stack is closed and opened again, so
    the tags stay properly nested even for partly overlapping entities
    Закрывает сущности, заканчивающиеся на границе. Лежащая выше в стеке сущность закрывается и открывается снова,
    так что теги остаются вложенными правильно даже при частично пересекающихся сущностях
    Attributes:
        stack (list[_OpenTag]): currently open entities (changed in place)
        boundary (int): position in UTF-16 code units
        result (list[str]): output pieces (changed in place)
    """

    reopened: list[_OpenTag] = []
    while any(tag.end <= boundary for tag in stack):
        closed_tag = stack.pop()
        result.append(closed_tag.close_tag)
        if closed_tag.end > boundary:
            reopened.append(closed_tag)
    for reopened_tag in reversed(reopened):
        result.append(reopened_tag.open_tag)
        stack.append(reopened_tag)


def render_message_html(text: str | None, entities: Sequence[TypeMessageEntity] | None) -> str:
    """
    Converts the raw text of a message and its entities to safe HTML
    Преобразует исходный текст сообщения и его сущности в безопасный HTML
    Attributes:
        text (str | None): raw message text (`message.raw_text`), without formatting marks
        entities (Sequence[TypeMessageEntity] | None): message entities (`message.entities`)
    Returns:
        str: HTML; line breaks are <br> (except for code blocks)
    """

    if not text:
        return ''
    # Offsets and lengths of entities are counted in UTF-16 code units, not in Python characters
    # Смещения и длины сущностей считаются в кодовых единицах UTF-16, а не в символах Python
    units = text.encode('utf-16-le', errors='replace')
    tags = _collect_tags(units, entities)
    boundaries = sorted({0, len(units) // 2} | {tag.start for tag in tags} | {tag.end for tag in tags})
    result: list[str] = []
    stack: list[_OpenTag] = []
    position = 0
    for boundary in boundaries:
        if boundary > position:
            chunk = escape(units[2 * position:2 * boundary].decode('utf-16-le', errors='replace'))
            # Inside a code block the line breaks stay as they are / Внутри блока кода переводы строк остаются как есть
            result.append(chunk if any(tag.is_pre for tag in stack) else chunk.replace('\n', '<br>'))
            position = boundary
        _close_ended_tags(stack, boundary, result)
        for tag in tags:
            if tag.start == boundary:
                result.append(tag.open_tag)
                stack.append(tag)
    return ''.join(result)
