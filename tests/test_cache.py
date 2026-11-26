"""
Tests of the cache of previews: downloading to the cache, moving to the media directory when a message is saved,
cleaning by age and the cache report.
Тесты кэша превью: загрузка в кэш, перенос в директорию медиа при сохранении сообщения, очистка по возрасту и отчет.
"""

import os
from datetime import datetime, timedelta
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from config import GlobalConst, MessageFileTypes, ProjectDirs
from telegram_handler import TelegramHandler, TgFile
from utils import clean_cache, remove_empty_dirs

FILE_PATH = 'chat_1/2026-01-02/photo.jpg'


def make_tg_file(size: int = 10) -> TgFile:
    """A file of a message with the path in the media directory / Файл сообщения с путем в директории медиа"""
    return TgFile(dialog_id=1, message_grouped_id='g', message=MagicMock(), message_id=1, description='',
                  file_name='photo.jpg', file_path=FILE_PATH, alt_text='Image', size=size,
                  file_type=MessageFileTypes.IMAGE)


def make_handler() -> SimpleNamespace:
    """Handler stub: `_run` returns what the fake `download_media` has written / Заглушка обработчика"""
    def download_media(**params):
        Path(params['file']).write_bytes(b'x')
        return str(params['file'])

    return SimpleNamespace(client=SimpleNamespace(download_media=MagicMock(side_effect=download_media)),
                           _run=lambda value: value)


def test_preview_is_downloaded_to_the_cache_not_to_the_media_directory(work_dir: Path):
    handler = make_handler()
    tg_file = make_tg_file()
    assert TelegramHandler.download_message_file(handler, tg_file, to_cache=True)
    assert (ProjectDirs.cache_dir / 'previews' / FILE_PATH).exists()
    assert not (ProjectDirs.media_dir / FILE_PATH).exists()
    assert tg_file.is_cached() and not tg_file.is_exists()
    # The second call does not download it again / Повторный вызов не скачивает файл заново
    TelegramHandler.download_message_file(handler, tg_file, to_cache=True)
    assert handler.client.download_media.call_count == 1


def test_saving_moves_the_preview_to_the_media_directory(work_dir: Path):
    handler = make_handler()
    tg_file = make_tg_file()
    TelegramHandler.download_message_file(handler, tg_file, to_cache=True)
    assert TelegramHandler.download_message_file(handler, tg_file) == FILE_PATH
    assert (ProjectDirs.media_dir / FILE_PATH).read_bytes() == b'x'
    assert not (ProjectDirs.cache_dir / 'previews' / FILE_PATH).exists()
    assert handler.client.download_media.call_count == 1  # Moved, not downloaded again / Перенесен, а не скачан
    # The empty directories of the preview are gone, the `previews` directory and the cache stay
    # Пустые каталоги превью удалены, каталог `previews` и кэш остаются
    assert (ProjectDirs.cache_dir / 'previews').is_dir()
    assert not (ProjectDirs.cache_dir / 'previews' / 'chat_1').exists()


def test_remove_empty_dirs_stops_at_a_non_empty_directory_and_at_the_limit(tmp_path: Path):
    deep = tmp_path / 'a' / 'b' / 'c'
    deep.mkdir(parents=True)
    (tmp_path / 'a' / 'keep.txt').write_text('x', encoding='utf-8')
    remove_empty_dirs(deep, tmp_path)
    assert not (tmp_path / 'a' / 'b').exists() and (tmp_path / 'a').exists()
    outside = tmp_path.parent / 'outside_dir_for_test'
    outside.mkdir(exist_ok=True)
    remove_empty_dirs(outside, tmp_path)  # Not inside `stop`: untouched / Вне `stop`: не тронут
    assert outside.exists()
    outside.rmdir()


def test_saving_without_preview_downloads_to_the_media_directory(work_dir: Path):
    handler = make_handler()
    assert TelegramHandler.download_message_file(handler, make_tg_file())
    assert (ProjectDirs.media_dir / FILE_PATH).exists()
    assert not (ProjectDirs.cache_dir / 'previews').exists()


def test_too_big_file_is_not_downloaded(work_dir: Path):
    handler = make_handler()
    big = make_tg_file(GlobalConst.button_download_size + 1)
    assert TelegramHandler.download_message_file(handler, big, to_cache=True) is None
    handler.client.download_media.assert_not_called()


def age_file(path: Path, days: int, now: datetime) -> None:
    """Sets the modification time `days` ago / Задает время изменения `days` дней назад"""
    stamp = (now - timedelta(days=days)).timestamp()
    os.utime(path, (stamp, stamp))


def test_clean_cache_deletes_old_files_and_empty_directories_but_not_avatars(tmp_path: Path):
    now = datetime(2026, 6, 1)
    old = tmp_path / 'previews' / 'chat' / 'group' / 'old.jpg'
    fresh = tmp_path / 'previews' / 'chat2' / 'fresh.jpg'
    avatar = tmp_path / GlobalConst.cache_avatars_dir / '5' / '77.jpg'
    for path in (old, fresh, avatar):
        path.parent.mkdir(parents=True)
        path.write_bytes(b'x')
    age_file(old, GlobalConst.cache_max_age_days + 1, now)
    age_file(fresh, GlobalConst.cache_max_age_days - 1, now)
    age_file(avatar, 365, now)
    assert clean_cache(tmp_path, GlobalConst.cache_max_age_days, now) == (1, [])
    assert not old.exists() and not old.parent.exists() and not (tmp_path / 'previews' / 'chat').exists()
    assert fresh.exists() and avatar.exists()


def test_clean_cache_without_directory(tmp_path: Path):
    assert clean_cache(tmp_path / 'missing', 30) == (0, [])


# ----------------------------------------------------------------------------------------------------------------------
# Chat avatars / Аватарки чатов
# ----------------------------------------------------------------------------------------------------------------------

def make_dialog(dialog_id: int, photo_id: int | None) -> SimpleNamespace:
    """A Telegram dialog with an avatar (or without it) / Диалог Telegram с аватаркой (или без нее)"""
    return SimpleNamespace(dialog_id=dialog_id, photo_id=photo_id, entity=SimpleNamespace(id=dialog_id))


async def fake_download(_entity, file, download_big):
    """The fake `download_profile_photo`: writes the file / Заглушка `download_profile_photo`: пишет файл"""
    assert download_big is False  # The small photo only / Только маленькое фото
    Path(file).write_bytes(b'jpg')
    return str(file)


def make_avatar_handler(download=fake_download) -> SimpleNamespace:
    """Handler stub with a fake client and `_run` that runs the coroutine / Заглушка обработчика"""
    import asyncio
    return SimpleNamespace(client=SimpleNamespace(download_profile_photo=MagicMock(side_effect=download)),
                           _run=lambda coro: asyncio.run(coro))


def avatar_path(dialog_id: int, photo_id: int) -> Path:
    return ProjectDirs.cache_dir / GlobalConst.cache_avatars_dir / str(dialog_id) / f'{photo_id}.jpg'


def test_avatars_are_downloaded_only_when_the_photo_is_new(work_dir: Path):
    handler = make_avatar_handler()
    dialogs = [make_dialog(1, 100), make_dialog(-1002, 200), make_dialog(3, None)]
    TelegramHandler.sync_avatars(handler, dialogs)
    assert avatar_path(1, 100).exists() and avatar_path(-1002, 200).exists()
    assert not (ProjectDirs.cache_dir / GlobalConst.cache_avatars_dir / '3').exists()  # No photo / Нет фото
    assert handler.client.download_profile_photo.call_count == 2
    # The same list again: everything is in the cache, no requests / Тот же список: все в кэше, запросов нет
    TelegramHandler.sync_avatars(handler, dialogs)
    assert handler.client.download_profile_photo.call_count == 2


def test_changed_photo_replaces_the_old_avatar(work_dir: Path):
    handler = make_avatar_handler()
    TelegramHandler.sync_avatars(handler, [make_dialog(1, 100)])
    TelegramHandler.sync_avatars(handler, [make_dialog(1, 101)])
    assert avatar_path(1, 101).exists() and not avatar_path(1, 100).exists()
    TelegramHandler.sync_avatars(handler, [make_dialog(1, None)])  # The photo was removed / Фото удалили
    assert not avatar_path(1, 101).parent.exists()


def test_failed_avatar_does_not_stop_the_others_and_leaves_no_partial_file(work_dir: Path):
    async def flaky(entity, file, download_big):
        if entity.id == 1:
            Path(file).write_bytes(b'part')
            raise ConnectionError('lost')
        return await fake_download(entity, file, download_big)

    handler = make_avatar_handler(flaky)
    TelegramHandler.sync_avatars(handler, [make_dialog(1, 100), make_dialog(2, 200)])
    assert not list((ProjectDirs.cache_dir / GlobalConst.cache_avatars_dir / '1').glob('*'))
    assert avatar_path(2, 200).exists()


def test_avatar_url_and_stub():
    from utils import avatar_color, avatar_initials, find_avatar
    assert avatar_initials('Ivan Petrov Sidorov') == 'IP'
    assert avatar_initials('Saved Messages (Favorites)') == 'SM'
    assert avatar_initials('Кот') == 'К'
    assert avatar_initials('<No Title>') == 'NT'
    assert avatar_initials('') == '?' and avatar_initials(None) == '?' and avatar_initials('🙂') == '?'
    assert avatar_color(5) == avatar_color(5) and avatar_color(-5) == avatar_color(5)
    assert avatar_color(1) != avatar_color(2)
    assert find_avatar(ProjectDirs.cache_dir, 424242) is None


def test_lists_show_the_avatar_or_the_stub(client: TestClient, tg_handler: SimpleNamespace):
    """The Telegram list and the database rows use the cache: the photo if it is there, else the initials"""
    avatar_path(1, 100).parent.mkdir(parents=True)
    avatar_path(1, 100).write_bytes(b'jpg')
    tg_handler.current_state.dialog_list = [SimpleNamespace(dialog_id=1, title='First chat'),
                                            SimpleNamespace(dialog_id=-2, title='Second chat')]
    html = client.get('/').text
    assert 'src="/cache/_avatars/1/100.jpg"' in html
    assert '>SC</span>' in html  # The stub of the chat without a photo / Заглушка чата без фото
    assert client.get('/cache/_avatars/1/100.jpg').content == b'jpg'


def test_telegram_details_show_the_avatar_before_the_chat_title(client: TestClient, tg_handler: SimpleNamespace):
    """The details of the Telegram tab show the chat avatar (small) like the database tab does"""
    from tests.test_telegram_routes import CHANNEL_ID, make_details
    avatar_path(CHANNEL_ID, 7).parent.mkdir(parents=True)
    avatar_path(CHANNEL_ID, 7).write_bytes(b'jpg')
    tg_handler.get_message_detail.return_value = make_details()
    html = client.get(f'/tg_details/{CHANNEL_ID}/{CHANNEL_ID}_1').json()['tg_details']
    assert f'class="avatar avatar-small" src="/cache/_avatars/{CHANNEL_ID}/7.jpg"' in html


def test_saved_html_has_the_avatar_inside_the_file(client: TestClient, db_handler):
    """The HTML file of a saved message is standalone: the avatar is a `data:` address, or the initials circle"""
    from starlette.requests import Request
    from database_handler import DbDialog, DbMessageGroup
    from web.main import app
    from web.message_html import write_message_html
    db_handler.session.add(DbDialog(dialog_id=7, title='Ivan Petrov', dialog_type_id=1))
    group = DbMessageGroup(grouped_id='7_1', date=datetime(2026, 1, 2), html='Hi', plain_text='Hi',
                           truncated_text='Hi', sender_id=1, dialog_id=7)
    db_handler.session.add(group)
    db_handler.session.flush()
    request = Request({'type': 'http', 'app': app, 'router': app.router, 'method': 'GET', 'path': '/', 'headers': [],
                       'server': ('127.0.0.1', 5000), 'scheme': 'http', 'query_string': b''})
    target = ProjectDirs.media_dir / 'chat' / 'message.html'
    # No avatar in the cache: the circle with the initials / Аватарки в кэше нет: круг с инициалами
    write_message_html(request, group, target)
    content = target.read_text(encoding='utf-8')
    assert 'avatar-stub' in content and '>IP</span>' in content and 'data:image' not in content
    # With the avatar in the cache: embedded, the file does not link to the cache / Аватарка встроена в файл
    avatar_path(7, 5).parent.mkdir(parents=True)
    avatar_path(7, 5).write_bytes(b'jpgdata')
    write_message_html(request, group, target)
    content = target.read_text(encoding='utf-8')
    assert 'src="data:image/jpeg;base64,anBnZGF0YQ=="' in content and '/cache/' not in content
