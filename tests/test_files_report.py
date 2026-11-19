"""
Tests of the files summary line of a message group (`2 Images, Video`): the function that forms it, the Telegram group
that uses it and the database list that forms it at display time from the files of the group (the stored
`files_report` column is not read), with the files loaded by one query for the whole list.
Тесты строки-резюме файлов группы сообщений (`2 Images, Video`): функция, которая ее формирует, группа Telegram, которая
ее использует, и список БД, который формирует ее при показе по файлам группы (сохраненный столбец `files_report` не
читается), причем файлы загружаются одним запросом на весь список.
"""

from datetime import datetime
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from configs.config import DialogTypes, MessageFileTypes
from database_handler import DatabaseHandler, DbCurrentState, DbDialog, DbFile, DbMessageGroup, DbMessageSortFilter
from telegram_handler import TgMessageGroup
from utils import format_files_report

IMAGE = MessageFileTypes.IMAGE
PHOTO = MessageFileTypes.PHOTO
VIDEO = MessageFileTypes.VIDEO
THUMBNAIL = MessageFileTypes.THUMBNAIL
AUDIO = MessageFileTypes.AUDIO
CONTENT = MessageFileTypes.CONTENT
UNKNOWN = MessageFileTypes.UNKNOWN


def ids(*file_types: MessageFileTypes) -> list[int]:
    """Type IDs of the given file types, as the function takes them / ID заданных типов файлов"""
    return [file_type.type_id for file_type in file_types]


@pytest.fixture(autouse=True)
def fresh_state(db_handler: DatabaseHandler) -> None:
    """The filter and the current state are class attributes of the handler: give the test its own"""
    db_handler.message_sort_filter = DbMessageSortFilter()
    db_handler.current_state = DbCurrentState()


# ----------------------------------------------------------------------------------------------------------------------
# The function / Функция
# ----------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('file_types, expected', [
    ((), ''),
    ((IMAGE,), 'Image'),
    ((IMAGE, VIDEO), 'Image, Video'),
    ((IMAGE, IMAGE), '2 Images'),
    ((VIDEO, IMAGE, VIDEO, IMAGE), '2 Images, 2 Videos'),
    ((VIDEO, IMAGE, IMAGE), '2 Images, Video'),
    ((VIDEO, IMAGE, VIDEO), 'Image, 2 Videos'),
    ((IMAGE,) * 10, '10 Images'),
    ((VIDEO, AUDIO, IMAGE), 'Audio, Image, Video'),
    ((UNKNOWN, UNKNOWN), '2 Unknowns'),
    ((PHOTO, IMAGE), '2 Images'),  # the photo and the image document have the same name
])
def test_format_files_report(file_types: tuple[MessageFileTypes, ...], expected: str):
    """The number and the plural form only for several files, the types in alphabetical order, none for no files"""
    assert format_files_report(ids(*file_types)) == expected


def test_format_files_report_skips_the_content_file():
    """The service HTML file of the message is not a message file: it is not in the line"""
    assert format_files_report(ids(CONTENT, IMAGE, IMAGE)) == '2 Images'
    assert format_files_report(ids(CONTENT)) == ''


def test_format_files_report_does_not_count_video_thumbnails():
    """The preview picture of a video is not a picture of its own: where there is a video, no extra Image appears"""
    assert format_files_report(ids(VIDEO, THUMBNAIL)) == 'Video'
    assert format_files_report(ids(VIDEO, THUMBNAIL, VIDEO, THUMBNAIL)) == '2 Videos'
    assert format_files_report(ids(IMAGE, VIDEO, THUMBNAIL)) == 'Image, Video'
    assert format_files_report(ids(THUMBNAIL)) == ''


def test_format_files_report_takes_any_iterable():
    """A generator works too (the callers pass one)"""
    assert format_files_report(type_id for type_id in ids(VIDEO, VIDEO)) == '2 Videos'


# ----------------------------------------------------------------------------------------------------------------------
# The Telegram group / Группа Telegram
# ----------------------------------------------------------------------------------------------------------------------

def test_telegram_group_report():
    """The Telegram group forms the line from its files (`2 Images, Video`)"""
    group = TgMessageGroup('42_1', 42)
    group.files = [SimpleNamespace(file_type=file_type) for file_type in (VIDEO, THUMBNAIL, IMAGE, PHOTO)]
    group.set_files_report()
    assert group.files_report == '2 Images, Video'  # the video thumbnail is not counted
    group.files = []
    group.set_files_report()
    assert group.files_report == ''


# ----------------------------------------------------------------------------------------------------------------------
# The database list / Список БД
# ----------------------------------------------------------------------------------------------------------------------

def add_group(handler: DatabaseHandler, number: int, file_types: tuple[MessageFileTypes, ...],
              stored_report: str = '') -> str:
    """Adds a message group with files of the given types (the stored `files_report` is the given one); returns its ID
    Добавляет группу сообщений с файлами заданных типов (сохраненный `files_report` - заданный); возвращает ее ID"""
    session = handler.session
    if session.get(DbDialog, 1) is None:
        session.add(DbDialog(dialog_id=1, title='Chat', dialog_type_id=DialogTypes.CHANNEL.value))
    grouped_id = f'1_{number}'
    group = DbMessageGroup(grouped_id=grouped_id, date=datetime(2026, 1, number, 3, 4, 5), html='text',
                           plain_text='text', truncated_text='text', files_report=stored_report, sender_id=7, dialog_id=1)
    for index, file_type in enumerate(file_types):
        group.files.append(DbFile(file_path=f'chat/{number}_{index}{file_type.default_ext}', message_id=number, size=10,
                                  file_type_id=file_type.type_id))
    session.add(group)
    session.commit()
    return grouped_id


def list_html(client: TestClient) -> str:
    """The list of the database messages as the filter route returns it / Список сообщений БД, как его отдает роут"""
    return client.post('/db_message_apply_filters', data={}).json()['db_messages']


def test_database_list_forms_the_line_from_the_files(client: TestClient, db_handler: DatabaseHandler):
    """The line comes from the files of the group (the service Content file is skipped), not from the stored column"""
    add_group(db_handler, 1, (IMAGE, IMAGE, VIDEO, THUMBNAIL, CONTENT), stored_report='Image (2) Video')
    add_group(db_handler, 2, (VIDEO, CONTENT), stored_report='something old')
    add_group(db_handler, 3, (CONTENT,), stored_report='stored text')
    add_group(db_handler, 4, (AUDIO, UNKNOWN), stored_report='')
    html = list_html(client)
    assert '<b>2 Images, Video</b>' in html  # the thumbnail of the video is not an Image
    assert '<b>Video</b>' in html
    assert '<b>Audio, Unknown</b>' in html
    for old in ('Image (2) Video', 'something old', 'stored text'):
        assert old not in html
    # A group with the service file only has no line at all (3 of the 4 groups have one)
    assert html.count('<b>') == 3


def test_database_details_report_is_formed_from_the_files(db_handler: DatabaseHandler):
    """The message details carry the formed line too"""
    grouped_id = add_group(db_handler, 1, (IMAGE, IMAGE, VIDEO, CONTENT), stored_report='old')
    assert db_handler.get_message_detail(grouped_id)['files_report'] == '2 Images, Video'


def test_database_list_loads_files_with_a_constant_number_of_queries(db_handler: DatabaseHandler):
    """The files and their types are loaded for the whole list at once: more groups, the same number of SELECTs"""
    def selects_for_list() -> int:
        statements: list[str] = []

        def record(_conn, _cursor, statement, *_args):
            if statement.lstrip().upper().startswith('SELECT'):
                statements.append(statement)

        event.listen(db_handler.engine, 'before_cursor_execute', record)
        try:
            db_handler.session.expire_all()
            groups = db_handler.get_message_group_list()
            lines = [format_files_report(db_file.file_type_id for db_file in group.files) for group in groups]
        finally:
            event.remove(db_handler.engine, 'before_cursor_execute', record)
        assert all(lines)
        return len(statements)

    for number in (1, 2):
        add_group(db_handler, number, (IMAGE, VIDEO))
    few = selects_for_list()
    for number in range(3, 9):
        add_group(db_handler, number, (IMAGE, IMAGE, VIDEO))
    assert selects_for_list() == few
