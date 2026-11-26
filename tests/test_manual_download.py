"""
Tests of the download of the message files by size: the level of a file (automatic, by the button, "Download anyway"),
the files that wait for the button, the percent in the status bar, the route, the buttons in the details, the saving
of a message and the maintenance.
Тесты загрузки файлов сообщения по размеру: уровень файла (автоматически, по кнопке, «Download anyway»), файлы, ждущие
кнопки, процент в строке статуса, роут, кнопки в деталях, сохранение сообщения и сервисное обслуживание.
"""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient
from config import DialogTypes, GlobalConst, MessageFileTypes, ProjectDirs
from telegram_handler import (DOWNLOAD_AUTO, DOWNLOAD_BUTTON, DOWNLOAD_CONFIRM, DOWNLOAD_NONE, TelegramHandler,
                              TgFile)
from tests.test_telegram_routes import CHANNEL_ID, make_details
from utils import status_messages

MB = 2 ** 20
AUTO = GlobalConst.auto_preview_size
BUTTON = GlobalConst.button_download_size


def make_tg_file(file_type: MessageFileTypes, size: int, name: str = 'f.bin') -> TgFile:
    return TgFile(dialog_id=1, message_grouped_id='g', message=MagicMock(), message_id=1, description='',
                  file_name=name, file_path=f'chat_1/2026-01-02/{name}', alt_text=file_type.alt_text, size=size,
                  file_type=file_type)


def make_handler(files: list[TgFile], download=None) -> SimpleNamespace:
    """Handler stub with a message group of the files; `download` replaces `download_message_file`"""
    group = SimpleNamespace(date=datetime(2026, 1, 2), html='', files=files, files_report='', saved_to_db=False)
    handler = SimpleNamespace(
        current_state=SimpleNamespace(message_group_list=[group]),
        get_message_group_by_id=lambda groups, group_id: groups[0],
        get_dialog_by_id=lambda dialog_id: SimpleNamespace(title='Chat'),
        download_message_file=download or MagicMock(return_value='path'))
    handler.get_message_detail = lambda dialog_id, group_id: TelegramHandler.get_message_detail(
        handler, dialog_id, group_id)  # type: ignore[arg-type]
    return handler


# ----------------------------------------------------------------------------------------------------------------------
# The level of a file / Уровень файла
# ----------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize('file_type, size, level', [
    (MessageFileTypes.VIDEO, 0, DOWNLOAD_NONE),
    (MessageFileTypes.VIDEO, AUTO, DOWNLOAD_AUTO),
    (MessageFileTypes.VIDEO, AUTO + 1, DOWNLOAD_BUTTON),
    (MessageFileTypes.UNKNOWN, BUTTON, DOWNLOAD_BUTTON),
    (MessageFileTypes.AUDIO, BUTTON + 1, DOWNLOAD_CONFIRM),
    # A picture is automatic up to the size of the button / Картинка автоматическая до размера кнопки
    (MessageFileTypes.PHOTO, BUTTON, DOWNLOAD_AUTO),
    (MessageFileTypes.THUMBNAIL, AUTO + 1, DOWNLOAD_AUTO),
    (MessageFileTypes.IMAGE, BUTTON + 1, DOWNLOAD_CONFIRM),
])
def test_download_level_follows_the_size(file_type: MessageFileTypes, size: int, level: str):
    assert make_tg_file(file_type, size).download_level == level


@pytest.mark.parametrize('file_type, name, label', [
    (MessageFileTypes.VIDEO, 'v.mp4', 'video'),
    (MessageFileTypes.AUDIO, 'a.mp4', 'audio'),
    (MessageFileTypes.UNKNOWN, 'doc.pdf', 'PDF'),
    (MessageFileTypes.UNKNOWN, 'big.tar.gz', 'GZ'),
    (MessageFileTypes.UNKNOWN, 'noext.unk', 'file'),  # The extension is unknown / Расширение неизвестно
    (MessageFileTypes.UNKNOWN, 'noext', 'file'),
])
def test_type_label_shows_the_extension_of_an_unknown_file(file_type: MessageFileTypes, name: str, label: str):
    """The buttons name the type of a file of an unknown type by its extension, if it is known"""
    assert make_tg_file(file_type, 10, name).type_label == label


# ----------------------------------------------------------------------------------------------------------------------
# Details and the button / Детали и кнопка
# ----------------------------------------------------------------------------------------------------------------------

def test_details_download_the_small_files_and_wait_for_the_others(work_dir):
    """The small files (and the pictures up to the limit) go to the cache at once; the others wait for the button"""
    files = [make_tg_file(MessageFileTypes.UNKNOWN, 10, 'small.pdf'),
             make_tg_file(MessageFileTypes.PHOTO, 10 * MB, 'photo.jpg'),
             make_tg_file(MessageFileTypes.VIDEO, 10 * MB, 'v.mp4'),
             make_tg_file(MessageFileTypes.AUDIO, 4 * MB, 'a.mp4'),
             make_tg_file(MessageFileTypes.UNKNOWN, BUTTON + 1, 'big.zip'),
             make_tg_file(MessageFileTypes.UNKNOWN, 0, 'nosize.bin')]
    handler = make_handler(files)
    details = TelegramHandler.get_message_detail(handler, 1, 'g')  # type: ignore[arg-type]
    assert [call.args[0].file_name for call in handler.download_message_file.call_args_list] == [
        'small.pdf', 'photo.jpg']
    assert [tg_file.file_name for tg_file in details['pending_files']] == ['v.mp4', 'a.mp4', 'big.zip']
    assert 'too_large_files' not in details


def test_download_pending_file_shows_percent_and_returns_the_details(work_dir):
    """The progress goes to the status bar only when the 5-percent step changes; the details are built again"""
    video = make_tg_file(MessageFileTypes.VIDEO, 10 * MB, 'v.mp4')
    versions = []

    def download(tg_file, to_cache=False, progress_callback=None, ignore_limit=False):
        assert to_cache and tg_file is video and ignore_limit
        for current in (10, 11, 12, 500, 1000):
            progress_callback(current, 1000)
            versions.append((status_messages.version, status_messages.messages['sb_operation']))
        return 'path'

    handler = make_handler([video], download)
    details = TelegramHandler.download_pending_file(handler, 1, 'g', video.file_path)  # type: ignore[arg-type]
    assert details['message_group_id'] == 'g'
    # 1%, 1%, 1% are one step (the status is written once), then 50% and 100%
    # 1%, 1%, 1% - один шаг (статус пишется один раз), затем 50% и 100%
    assert versions[0][0] == versions[1][0] == versions[2][0] < versions[3][0] < versions[4][0]
    assert 'sb-progress">1%</span> <span class="sb-operation-text"' in versions[0][1]
    assert '>50%<' in versions[3][1] and '>100%<' in versions[4][1]
    # The percent is right after the spinner, before the operation text / Процент сразу после крутилки
    assert versions[3][1].index('sb-spinner') < versions[3][1].index('50%') < versions[3][1].index('Downloading video')
    # The end of the operation clears the percent / Конец операции убирает процент
    assert 'sb-progress' not in status_messages.messages['sb_operation']


def test_download_pending_file_takes_a_big_file_and_refuses_the_others(work_dir):
    """A file over the limit is downloaded by the button too; the automatic files and the ones of an unknown size are
    not for the button; a failed download is an error"""
    big = make_tg_file(MessageFileTypes.UNKNOWN, 300 * MB, 'big.zip')
    small = make_tg_file(MessageFileTypes.UNKNOWN, 10, 'small.pdf')
    nosize = make_tg_file(MessageFileTypes.UNKNOWN, 0, 'nosize.bin')
    video = make_tg_file(MessageFileTypes.VIDEO, 10 * MB, 'v.mp4')
    handler = make_handler([big, small, nosize, video], MagicMock(return_value=None))
    for file in (small, nosize):
        with pytest.raises(LookupError):
            TelegramHandler.download_pending_file(handler, 1, 'g', file.file_path)  # type: ignore[arg-type]
    with pytest.raises(LookupError):
        TelegramHandler.download_pending_file(handler, 1, 'g', 'no/such/file')  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        TelegramHandler.download_pending_file(handler, 1, 'g', big.file_path)  # type: ignore[arg-type]
    assert handler.download_message_file.call_args.kwargs['ignore_limit'] is True


def test_progress_callback_goes_to_telethon(work_dir):
    """`download_message_file` passes the callback to `download_media` / Колбэк передается в `download_media`"""
    def download_media(**params):
        params['progress_callback'](1, 2)
        return 'x'

    handler = SimpleNamespace(client=SimpleNamespace(download_media=MagicMock(side_effect=download_media)),
                              _run=lambda value: value)
    callback = MagicMock()
    video = make_tg_file(MessageFileTypes.VIDEO, 10, 'v.mp4')
    TelegramHandler.download_message_file(handler, video, to_cache=True,  # type: ignore[arg-type]
                                          progress_callback=callback)
    callback.assert_called_once_with(1, 2)


def test_the_limit_is_ignored_only_on_request(work_dir):
    """A big file is not downloaded by default, but is downloaded with `ignore_limit`; an unknown size never is"""
    handler = SimpleNamespace(client=SimpleNamespace(download_media=MagicMock(return_value='x')),
                              _run=lambda value: value)
    big = make_tg_file(MessageFileTypes.UNKNOWN, BUTTON + 1, 'big.zip')
    assert TelegramHandler.download_message_file(handler, big, to_cache=True) is None  # type: ignore[arg-type]
    assert TelegramHandler.download_message_file(handler, big, to_cache=True,  # type: ignore[arg-type]
                                                 ignore_limit=True) == 'x'
    nosize = make_tg_file(MessageFileTypes.UNKNOWN, 0, 'nosize.bin')
    assert TelegramHandler.download_message_file(handler, nosize, to_cache=True,  # type: ignore[arg-type]
                                                 ignore_limit=True) is None


def test_route_downloads_and_returns_the_details(client: TestClient, tg_handler: SimpleNamespace):
    tg_handler.download_pending_file = MagicMock(return_value=make_details())
    group_id = f'{CHANNEL_ID}_1'
    response = client.post(f'/tg_download_file/{CHANNEL_ID}/{group_id}', params={'file_path': 'chat/a b.mp4'})
    assert response.status_code == 200 and set(response.ui()) == {'tg_details'}
    tg_handler.download_pending_file.assert_called_once_with(CHANNEL_ID, group_id, 'chat/a b.mp4')
    assert tg_handler.current_state.message_details['message_group_id'] == group_id


def test_route_unknown_file_is_404_and_path_is_required(client: TestClient, tg_handler: SimpleNamespace):
    tg_handler.download_pending_file = MagicMock(side_effect=LookupError('no file'))
    url = f'/tg_download_file/{CHANNEL_ID}/{CHANNEL_ID}_1'
    assert client.post(url, params={'file_path': 'x'}).status_code == 404
    assert client.post(url).status_code == 422


def test_details_show_the_buttons(client: TestClient, tg_handler: SimpleNamespace):
    """A button with the size for each waiting file; a file over the limit has "Download anyway" with a question"""
    details = make_details()
    details['pending_files'] = [make_tg_file(MessageFileTypes.VIDEO, 3 * MB + 1024, 'clip 1.mp4'),
                                make_tg_file(MessageFileTypes.UNKNOWN, 150 * MB, 'big.zip')]
    tg_handler.get_message_detail.return_value = details
    html = client.get(f'/tg_details/{CHANNEL_ID}/{CHANNEL_ID}_1').ui()['tg_details']
    assert f'/tg_download_file/{CHANNEL_ID}/{CHANNEL_ID}_1?file_path=chat_1/2026-01-02/clip%201.mp4' in html
    assert 'Download video (3.0 MB)' in html
    assert 'Size 150.0 MB (ZIP). Download anyway' in html and "confirm('Size 150.0 MB." in html
    assert 'larger than the limit' not in html  # The old note is gone / Прежней пометки больше нет


def test_video_button_stands_above_its_own_thumbnail(client: TestClient, tg_handler: SimpleNamespace):
    """Each video button is inside the area of the thumbnail of the same message (above the picture); a file without
    a preview (unknown type) and a video without a thumbnail have their buttons above all the files"""
    def make_file(file_type: MessageFileTypes, message_id: int, name: str) -> TgFile:
        tg_file = make_tg_file(file_type, 10 * MB, name)
        tg_file.message_id = message_id
        return tg_file

    details = make_details()
    thumbnail = make_file(MessageFileTypes.THUMBNAIL, 1, 'one.jpg')
    thumbnail.alt_text = 'Image'
    details['existing_files'] = [make_file(MessageFileTypes.IMAGE, 5, 'plain.jpg'), thumbnail]
    details['pending_files'] = [make_file(MessageFileTypes.VIDEO, 1, 'one.mp4'),
                                make_file(MessageFileTypes.VIDEO, 2, 'two.mp4'),
                                make_file(MessageFileTypes.UNKNOWN, 3, 'doc.pdf')]
    tg_handler.get_message_detail.return_value = details
    html = client.get(f'/tg_details/{CHANNEL_ID}/{CHANNEL_ID}_1').ui()['tg_details']
    area = html.index('class="media-files-area"')
    button = {name: html.index(f'file_path=chat_1/2026-01-02/{name}') for name in ('one.mp4', 'two.mp4', 'doc.pdf')}
    assert html.count('/tg_download_file/') == 3  # Each button once / Каждая кнопка один раз
    # The buttons of the files without a preview are above the area, the video of the thumbnail is inside it
    # Кнопки файлов без превьюшки над областью, видео миниатюры внутри нее
    assert button['two.mp4'] < area and button['doc.pdf'] < area < button['one.mp4']
    assert html.index('src="/cache/previews/chat_1/2026-01-02/one.jpg"') > button['one.mp4']


# ----------------------------------------------------------------------------------------------------------------------
# Saving a message / Сохранение сообщения
# ----------------------------------------------------------------------------------------------------------------------

def test_saving_skips_a_big_file_unless_it_is_in_the_cache(client: TestClient, tg_handler: SimpleNamespace,
                                                           db_handler, work_dir: Path):
    """The message is saved. A file within the limit is downloaded with the percent; a file over the limit is skipped
    with a line in the report, unless it was downloaded by "Download anyway" before (it is in the cache)"""
    from tests.test_save_route import CHECKBOX, DIALOG_ID, make_group
    dialog = SimpleNamespace(dialog_id=DIALOG_ID, title='Test chat', type=DialogTypes.CHANNEL, get_self_dir=lambda: 'chat')
    tg_handler.get_dialog_by_id = MagicMock(return_value=dialog)
    tg_handler.download_message_file = MagicMock(return_value='downloaded')
    group = make_group(1)
    small = group.files[0]
    big = TgFile(DIALOG_ID, group.grouped_id, None, 2, '', 'big.zip', 'chat/big.zip', 'Unknown', BUTTON + 1,  # type: ignore[arg-type]
                 MessageFileTypes.UNKNOWN)
    cached = TgFile(DIALOG_ID, group.grouped_id, None, 3, '', 'cached.zip', 'chat/cached.zip', 'Unknown',  # type: ignore[arg-type]
                    BUTTON + 1, MessageFileTypes.UNKNOWN)
    (ProjectDirs.cache_dir / cached.preview_path).parent.mkdir(parents=True)
    (ProjectDirs.cache_dir / cached.preview_path).write_bytes(b'x')
    group.files.extend([big, cached])
    tg_handler.current_state.message_group_list = [group]
    response = client.post('/tg_save_selected_message_to_db',
                           data={CHECKBOX: [f'{GlobalConst.select_in_telegram}{group.grouped_id}']})
    assert response.status_code == 200
    downloaded = [call.args[0] for call in tg_handler.download_message_file.call_args_list]
    assert downloaded == [small, cached]  # The big file is not requested / Большой файл не запрашивается
    assert all(call.kwargs.get('progress_callback') for call in tg_handler.download_message_file.call_args_list)
    report = '\n'.join(status_messages.report_list or [])
    assert 'chat/big.zip skipped' in report and 'Download anyway' in report
    assert 'chat/cached.zip skipped' not in report
