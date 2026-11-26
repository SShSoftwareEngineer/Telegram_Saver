"""
Tests of the text of the media without a person's text (`describe_media`: web page, poll, location, venue, contact),
its way into a message group, the display of audio and files of an unknown type, and the note about the files over the
download limit. Telethon objects are real types filled by hand, messages are fake objects.
Тесты текста медиа без текста человека (`describe_media`: веб-страница, опрос, геопозиция, место, контакт), его
попадания в группу сообщений, показа аудио и файлов неизвестного типа и пометки о файлах больше лимита.
Объекты Telethon - настоящие типы, заполненные вручную, сообщения - заглушки.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from telethon.tl.types import (GeoPoint, MessageMediaContact, MessageMediaGeo, MessageMediaGeoLive, MessageMediaPhoto,
                               MessageMediaPoll, MessageMediaVenue, MessageMediaWebPage, Poll, PollAnswer,
                               PollAnswerVoters, PollResults, TextWithEntities, WebPage)
from config import GlobalConst, MessageFileTypes
from media_text import describe_media
from telegram_handler import TelegramHandler, TgFile, TgMessageGroup
from web.deps import templates

GEO = GeoPoint(lat=50.45, long=30.52, access_hash=0)
MAP_LINK = 'https://www.openstreetmap.org/?mlat=50.45&amp;mlon=30.52#map=16/50.45/30.52'


def make_poll(quiz: bool = False, results: PollResults | None = None) -> MessageMediaPoll:
    """A poll with a question and two answers; the text is `TextWithEntities` as in new layers of Telegram"""
    answers = [PollAnswer(text=TextWithEntities('Yes <b>', []), option=b'1'),
               PollAnswer(text=TextWithEntities('No', []), option=b'2')]
    poll = Poll(id=1, question=TextWithEntities('Tea or coffee?', []), answers=answers, hash=0, quiz=quiz, closed=False)
    return MessageMediaPoll(poll=poll, results=results or PollResults())


def test_unsupported_media_and_no_media_have_no_text():
    """A photo, a missing media and a point that is not set give no text block"""
    assert describe_media(None) is None
    assert describe_media(MessageMediaPhoto()) is None
    assert describe_media(MessageMediaGeo(geo=SimpleNamespace())) is None


def test_contact_shows_name_and_phone_only():
    plain, html = describe_media(MessageMediaContact(phone_number='+380501234567', first_name='Ann', last_name='<b>',
                                                     vcard='BEGIN:VCARD', user_id=1))  # type: ignore[misc]
    assert plain == 'Contact: Ann <b>, +380501234567'
    assert html == 'Contact: Ann &lt;b&gt;, +380501234567'


def test_location_has_coordinates_and_a_map_link():
    plain, html = describe_media(MessageMediaGeo(geo=GEO))  # type: ignore[misc]
    assert plain.startswith('Location: 50.450000, 30.520000\nhttps://www.openstreetmap.org/')
    assert f'<a href="{MAP_LINK}"' in html and 'noopener' in html


def test_map_service_is_chosen_in_the_config(monkeypatch):
    """`GlobalConst.map_service`: Google Maps by the name (any case); OpenStreetMap by default and for an unknown name"""
    assert 'openstreetmap.org' in describe_media(MessageMediaGeo(geo=GEO))[0]  # type: ignore[index]
    monkeypatch.setattr(GlobalConst, 'map_service', 'Google')
    plain, html = describe_media(MessageMediaGeo(geo=GEO))  # type: ignore[misc]
    assert plain.endswith('https://www.google.com/maps?q=50.45,30.52')
    assert 'href="https://www.google.com/maps?q=50.45,30.52"' in html
    monkeypatch.setattr(GlobalConst, 'map_service', 'nowhere')
    assert 'openstreetmap.org' in describe_media(MessageMediaGeo(geo=GEO))[0]  # type: ignore[index]


def test_live_location_and_venue():
    live_plain, _ = describe_media(MessageMediaGeoLive(geo=GEO, period=60))  # type: ignore[misc]
    assert live_plain.startswith('Live location: 50.450000, 30.520000')
    venue = MessageMediaVenue(geo=GEO, title='Cafe <1>', address='Main st', provider='', venue_id='', venue_type='')
    plain, html = describe_media(venue)  # type: ignore[misc]
    assert plain.startswith('Venue: Cafe <1>, Main st\nLocation: 50.450000')
    assert html.startswith('Venue: Cafe &lt;1&gt;, Main st<br>Location:')


def test_poll_without_results_lists_question_and_answers():
    plain, html = describe_media(make_poll(quiz=True))  # type: ignore[misc]
    assert plain == 'Poll: Tea or coffee? (quiz)\n- Yes <b>\n- No'
    assert html == 'Poll: Tea or coffee? (quiz)<br>- Yes &lt;b&gt;<br>- No'


def test_poll_with_results_shows_votes_and_the_chosen_answer():
    results = PollResults(total_voters=5, results=[PollAnswerVoters(option=b'1', voters=3, chosen=True),
                                                   PollAnswerVoters(option=b'2', voters=2, correct=True)])
    plain, _ = describe_media(make_poll(results=results))  # type: ignore[misc]
    assert plain == 'Poll: Tea or coffee?\n- Yes <b>: 3 (chosen)\n- No: 2 (correct)\nTotal voters: 5'


def test_poll_question_as_a_plain_string_is_supported():
    media = make_poll()
    media.poll.question = 'Old layer?'
    assert describe_media(media)[0].startswith('Poll: Old layer?')  # type: ignore[index]


def test_web_page_is_the_link_and_the_shortened_description(monkeypatch):
    monkeypatch.setattr(GlobalConst, 'truncated_text_length', 20)
    page = WebPage(id=1, url='https://e.com/?a=1&b=2', display_url='e.com', hash=0,
                   description='<i>' + 'word ' * 20)
    plain, html = describe_media(MessageMediaWebPage(webpage=page))  # type: ignore[misc]
    assert plain.startswith('https://e.com/?a=1&b=2\n\n<i>') and plain.endswith('...')
    assert html.startswith('<a href="https://e.com/?a=1&amp;b=2"') and '<br><br>&lt;i&gt;' in html


# ----------------------------------------------------------------------------------------------------------------------
# Message group / Группа сообщений
# ----------------------------------------------------------------------------------------------------------------------

def make_message(media, file=None, text: str = '') -> SimpleNamespace:
    return SimpleNamespace(id=1, sender_id=1, raw_text=text, entities=None, media=media, file=file,
                           date=datetime(2026, 1, 2, 3, 4, 5))


def test_media_without_a_file_adds_its_text_to_the_group():
    """A poll has no file: its text is added next to the text typed by a person, and is found by the search"""
    group = TgMessageGroup('42_1', 42)
    group.add_message(make_message(make_poll(), text='Vote!'))  # type: ignore[arg-type]
    assert group.plain_text == 'Vote!\n\nPoll: Tea or coffee?\n- Yes <b>\n- No'
    assert group.html.startswith('Vote!<br><br>Poll: Tea or coffee?<br>')


def test_media_with_a_file_is_not_added_twice():
    """The text of a media with a file goes with the file (`add_message_file`), not in `add_message`"""
    page = WebPage(id=1, url='https://e.com', display_url='e.com', hash=0)
    group = TgMessageGroup('42_2', 42)
    group.add_message(make_message(MessageMediaWebPage(webpage=page), file=object()))  # type: ignore[arg-type]
    assert group.plain_text == ''


def test_web_page_without_a_picture_keeps_its_text():
    """No file, so the text is taken in `add_message` (before it was lost) / Нет файла: текст берется в add_message"""
    page = WebPage(id=1, url='https://e.com', display_url='e.com', hash=0)
    group = TgMessageGroup('42_3', 42)
    group.add_message(make_message(MessageMediaWebPage(webpage=page)))  # type: ignore[arg-type]
    assert group.plain_text == 'https://e.com'


# ----------------------------------------------------------------------------------------------------------------------
# Display of the files / Показ файлов
# ----------------------------------------------------------------------------------------------------------------------

def render_media_file(kind: str, many: bool = False, caption: bool = False) -> str:
    template = templates.env.from_string(
        "{% from 'media_file.html' import media_file with context %}"
        "{{ media_file(kind, '/media/a b.dat', 'a b.dat', 2048, many, caption) }}")
    return template.render(tg_file_types=MessageFileTypes, kind=kind, many=many, caption=caption)


def test_audio_is_a_player_and_unknown_file_is_a_download_link():
    audio = render_media_file(MessageFileTypes.AUDIO.alt_text)
    assert '<audio src="/media/a b.dat" controls' in audio and 'media-files-inline' in audio
    unknown = render_media_file(MessageFileTypes.UNKNOWN.alt_text)
    assert '<a href="/media/a b.dat" download="a b.dat">a b.dat</a>' in unknown and '2.0 kB' in unknown


def test_image_and_video_keep_their_columns_and_the_caption_is_optional():
    image = render_media_file(MessageFileTypes.IMAGE.alt_text)
    assert '<img' in image and 'media-files-one-column' in image and 'media-file-name' not in image
    video = render_media_file(MessageFileTypes.VIDEO.alt_text, many=True, caption=True)
    assert '<video' in video and 'media-files-two-column' in video and 'media-file-name' in video


def test_other_kinds_show_nothing():
    assert render_media_file(MessageFileTypes.CONTENT.alt_text).strip() == ''


# ----------------------------------------------------------------------------------------------------------------------
# Files over the limit / Файлы больше лимита
# ----------------------------------------------------------------------------------------------------------------------

def make_tg_file(file_type: MessageFileTypes, size: int) -> TgFile:
    return TgFile(dialog_id=1, message_grouped_id='g', message=MagicMock(), message_id=1, description='',
                  file_name='f.bin', file_path='chat_1/2026-01-02/f.bin', alt_text=file_type.alt_text, size=size,
                  file_type=file_type)


def test_details_list_the_files_over_the_limit(work_dir):
    """A big document is listed as not downloaded; a video (not downloaded on purpose) and a small file are not"""
    big = make_tg_file(MessageFileTypes.UNKNOWN, GlobalConst.max_download_file_size + 1)
    video = make_tg_file(MessageFileTypes.VIDEO, GlobalConst.max_download_file_size + 1)
    small = make_tg_file(MessageFileTypes.UNKNOWN, 10)
    group = SimpleNamespace(date=datetime(2026, 1, 2), html='', files=[big, video, small], files_report='',
                            saved_to_db=False)
    handler = SimpleNamespace(
        current_state=SimpleNamespace(message_group_list=[group]),
        get_message_group_by_id=lambda groups, group_id: groups[0],
        get_dialog_by_id=lambda dialog_id: SimpleNamespace(title='Chat'),
        download_message_file=MagicMock(return_value=None))
    details = TelegramHandler.get_message_detail(handler, 1, 'g')  # type: ignore[arg-type]
    assert details['too_large_files'] == [big]
