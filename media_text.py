"""
The text of a message that is not typed by a person but comes with the media of the message: a web page preview, a poll,
a location, a venue, a contact. Telegram gives it as structured fields; here it becomes a text block in two forms
(plain text for search and truncation, safe HTML for display), so every kind of media goes to the message group in
one way (`TgMessageGroup._append_text`). The result is kept in the message text, no database column is needed.
Текст сообщения, который набрал не человек, а который приходит с медиа сообщения: превью веб-страницы, опрос,
геопозиция, место, контакт. Telegram отдает его структурированными полями; здесь он превращается в текстовый блок
в двух видах (обычный текст для поиска и обрезки, безопасный HTML для показа), поэтому любое медиа попадает в группу
сообщений одним способом (`TgMessageGroup._append_text`). Результат хранится в тексте сообщения, столбец БД не нужен.

describe_media: builds the text block of the media of a message, or None if the media has no text
"""

from html import escape
from textwrap import shorten
from typing import Any, Callable
from telethon.tl.types import (MessageMediaContact, MessageMediaGeo, MessageMediaGeoLive, MessageMediaPoll,
                               MessageMediaVenue, MessageMediaWebPage)
from config import GlobalConst
from message_renderer import plain_text_to_html, render_link_html

# A text block: the plain text and the safe HTML / Текстовый блок: обычный текст и безопасный HTML
MediaText = tuple[str, str]

# The map services for the setting `GlobalConst.map_service` (the first one is the default)
# Сервисы карт для настройки `GlobalConst.map_service` (первый - по умолчанию)
MAP_URLS = {'openstreetmap': 'https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}',
            'google': 'https://www.google.com/maps?q={lat},{lon}'}


def get_map_url_template() -> str:
    """
    The link template of the map service chosen in `GlobalConst.map_service`; OpenStreetMap if the name is unknown
    Шаблон ссылки сервиса карт, выбранного в `GlobalConst.map_service`; OpenStreetMap, если имя неизвестно
    """

    return MAP_URLS.get(GlobalConst.map_service.strip().lower(), MAP_URLS['openstreetmap'])


def _text_of(value: Any) -> str:
    """
    Text of a Telethon field that is a string or, in new layers, `TextWithEntities` (the text is in `.text`)
    Текст поля Telethon, которое является строкой или (в новых слоях) `TextWithEntities` (текст в `.text`)
    """

    return str(getattr(value, 'text', value) or '')


def _join(blocks: list[MediaText], plain_separator: str = '\n', html_separator: str = '<br>') -> MediaText:
    """
    Joins the blocks: the plain texts and the HTMLs separately / Склеивает блоки: обычные тексты и HTML отдельно
    """

    return (plain_separator.join(plain for plain, _ in blocks if plain),
            html_separator.join(html for _, html in blocks if html))


def _plain_block(text: str) -> MediaText:
    """A block of plain text without links / Блок обычного текста без ссылок"""

    return text, plain_text_to_html(text)


def _describe_web_page(media: MessageMediaWebPage) -> MediaText | None:
    """
    A web page preview: the address as a link and the shortened description
    Превью веб-страницы: адрес ссылкой и сокращенное описание
    """

    page = media.webpage
    url = getattr(page, 'url', None)
    description = getattr(page, 'description', None)
    blocks: list[MediaText] = []
    if url:
        blocks.append((url, render_link_html(url, url)))
    if description:
        blocks.append(_plain_block(shorten(description, width=GlobalConst.truncated_text_length, placeholder='...')))
    return _join(blocks, '\n\n', '<br><br>') if blocks else None


def _location_block(geo: Any, prefix: str) -> MediaText | None:
    """
    Coordinates and a link to the map (OpenStreetMap or Google Maps by the setting, no scripts of the map are loaded); None if there is no point
    Координаты и ссылка на карту (OpenStreetMap или Google Maps по настройке, скрипты карты не загружаются); None, если точки нет
    """

    lat, lon = getattr(geo, 'lat', None), getattr(geo, 'long', None)
    if lat is None or lon is None:
        return None
    url = get_map_url_template().format(lat=lat, lon=lon)
    coordinates = f'{lat:.6f}, {lon:.6f}'
    return f'{prefix}: {coordinates}\n{url}', f'{escape(prefix)}: {escape(coordinates)}<br>{render_link_html(url, url)}'


def _describe_location(media: MessageMediaGeo | MessageMediaGeoLive | MessageMediaVenue) -> MediaText | None:
    """
    A location, a live location (the point at the moment of receiving) or a venue (a place with a title and address)
    Геопозиция, живая геопозиция (точка на момент получения) или место (с названием и адресом)
    """

    blocks: list[MediaText] = []
    if isinstance(media, MessageMediaVenue):
        title = ', '.join(filter(None, [media.title, media.address]))
        blocks.append(_plain_block(f'Venue: {title}'))
    location = _location_block(media.geo, 'Live location' if isinstance(media, MessageMediaGeoLive) else 'Location')
    if location:
        blocks.append(location)
    return _join(blocks) if blocks else None


def _describe_contact(media: MessageMediaContact) -> MediaText:
    """
    A contact: the name and the phone number (the vCard is not shown)
    Контакт: имя и номер телефона (vCard не показывается)
    """

    name = ' '.join(filter(None, [media.first_name, media.last_name]))
    return _plain_block('Contact: ' + ', '.join(filter(None, [name, media.phone_number])))


def _describe_poll(media: MessageMediaPoll) -> MediaText:
    """
    A poll: the question, the answers and, if Telegram gave the results, the number of votes of each answer.
    It is a snapshot at the moment of receiving the message.
    Опрос: вопрос, варианты и, если Telegram отдал итоги, число голосов за каждый вариант.
    Это снимок на момент получения сообщения.
    """

    poll = media.poll
    results = getattr(media.results, 'results', None) or []
    voters = {result.option: result for result in results}
    kinds = [kind for kind, enabled in (('quiz', getattr(poll, 'quiz', False)),
                                        ('multiple choice', getattr(poll, 'multiple_choice', False)),
                                        ('closed', getattr(poll, 'closed', False))) if enabled]
    lines = [f'Poll: {_text_of(poll.question)}' + (f' ({", ".join(kinds)})' if kinds else '')]
    for answer in poll.answers:
        line = f'- {_text_of(answer.text)}'
        result = voters.get(answer.option)
        if result is not None:
            line += f': {result.voters}' + (' (chosen)' if result.chosen else '') + (
                ' (correct)' if result.correct else '')
        lines.append(line)
    total_voters = getattr(media.results, 'total_voters', None)
    if total_voters is not None:
        lines.append(f'Total voters: {total_voters}')
    return _plain_block('\n'.join(lines))


# Kinds of media and their builders / Виды медиа и их построители
_DESCRIBERS: tuple[tuple[type, Callable[[Any], MediaText | None]], ...] = (
    (MessageMediaWebPage, _describe_web_page),
    (MessageMediaPoll, _describe_poll),
    (MessageMediaGeo, _describe_location),
    (MessageMediaGeoLive, _describe_location),
    (MessageMediaVenue, _describe_location),
    (MessageMediaContact, _describe_contact),
)


def describe_media(media: Any) -> MediaText | None:
    """
    Builds the text block of the media of a message
    Строит текстовый блок медиа сообщения
    Attributes:
        media (Any): `message.media` (None for a message without media)
    Returns:
        MediaText | None: (plain text, safe HTML), or None if the media is of another kind or has no text
    """

    for media_class, describer in _DESCRIBERS:
        if isinstance(media, media_class):
            return describer(media)
    return None
