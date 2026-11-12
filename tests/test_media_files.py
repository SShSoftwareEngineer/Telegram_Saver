"""
Tests of the media file helpers: cutting a report list and deleting files with the directories left empty.
Тесты помощников для файлов медиа: обрезка списка отчета и удаление файлов вместе с оставшимися пустыми директориями.
"""

from pathlib import Path
import pytest
from utils import delete_media_files, limit_list


def make_file(path: Path) -> Path:
    """Creates a file with its directories / Создает файл вместе с его директориями"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'data')
    return path


# ----------------------------------------------------------------------------------------------------------------------
# limit_list
# ----------------------------------------------------------------------------------------------------------------------

def test_limit_list_short_list_is_unchanged():
    """A list up to the limit has no continuation sign"""
    assert limit_list(['a', 'b'], 2) == ['a', 'b']
    assert limit_list([], 2) == []


def test_limit_list_long_list_is_cut_with_continuation_sign():
    """A longer list is cut to the limit and ends with '...'"""
    assert limit_list(['a', 'b', 'c'], 2) == ['a', 'b', '...']


# ----------------------------------------------------------------------------------------------------------------------
# delete_media_files
# ----------------------------------------------------------------------------------------------------------------------

def test_deletes_files_and_empty_directories_up_to_media_dir(tmp_path: Path):
    """The last file of a date directory: the date directory and the dialog directory go, the media directory stays"""
    media = tmp_path / 'media'
    make_file(media / 'chat_1' / '2026-01-01' / 'a.jpg')
    count, errors = delete_media_files(media, ['chat_1/2026-01-01/a.jpg'])
    assert (count, errors) == (1, [])
    assert media.is_dir() and list(media.iterdir()) == []


def test_non_empty_directory_stops_the_climb(tmp_path: Path):
    """A directory with a file of another message stays, and so does everything above it"""
    media = tmp_path / 'media'
    make_file(media / 'chat_1' / '2026-01-01' / 'a.jpg')
    make_file(media / 'chat_1' / '2026-01-01' / 'b.jpg')
    make_file(media / 'chat_1' / '2026-01-02' / 'c.jpg')
    count, errors = delete_media_files(media, ['chat_1/2026-01-01/a.jpg', 'chat_1/2026-01-02/c.jpg'])
    assert (count, errors) == (2, [])
    assert (media / 'chat_1' / '2026-01-01' / 'b.jpg').is_file()
    assert not (media / 'chat_1' / '2026-01-02').exists()
    assert (media / 'chat_1').is_dir()


def test_the_dialog_directory_with_other_dates_stays(tmp_path: Path):
    """The date directory is empty and goes; the dialog directory still has another date and stays"""
    media = tmp_path / 'media'
    make_file(media / 'chat_1' / '2026-01-01' / 'a.jpg')
    make_file(media / 'chat_1' / '2026-01-02' / 'c.jpg')
    delete_media_files(media, ['chat_1/2026-01-01/a.jpg'])
    assert not (media / 'chat_1' / '2026-01-01').exists()
    assert (media / 'chat_1' / '2026-01-02' / 'c.jpg').is_file()


def test_missing_file_is_not_an_error_and_empty_directory_is_removed(tmp_path: Path):
    """The file is already gone: nothing to delete, no error, but the empty directory is still removed"""
    media = tmp_path / 'media'
    (media / 'chat_1' / '2026-01-01').mkdir(parents=True)
    count, errors = delete_media_files(media, ['chat_1/2026-01-01/gone.jpg'])
    assert (count, errors) == (0, [])
    assert not (media / 'chat_1').exists() and media.is_dir()


def test_missing_directories_do_not_break_the_climb(tmp_path: Path):
    """Neither the file nor its directories exist (not even the media directory content): no error"""
    media = tmp_path / 'media'
    media.mkdir()
    assert delete_media_files(media, ['chat_1/2026-01-01/gone.jpg']) == (0, [])
    assert media.is_dir()


def test_path_outside_media_dir_is_never_touched(tmp_path: Path):
    """A path that leaves the media directory (or is the directory itself) is reported and nothing is deleted"""
    media = tmp_path / 'media'
    media.mkdir()
    outside = make_file(tmp_path / 'outside.jpg')
    count, errors = delete_media_files(media, ['../outside.jpg', '.'])
    assert count == 0
    assert errors == ['../outside.jpg: outside of the media directory', '.: outside of the media directory']
    assert outside.is_file() and media.is_dir()


def test_file_error_is_returned_and_the_work_goes_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A file that cannot be deleted: its error is returned, the file and its directory stay, the others are deleted"""
    media = tmp_path / 'media'
    make_file(media / 'chat_1' / '2026-01-01' / 'busy.jpg')
    make_file(media / 'chat_1' / '2026-01-02' / 'free.jpg')
    real_unlink = Path.unlink

    def unlink(self: Path, *args, **kwargs):
        if self.name == 'busy.jpg':
            raise PermissionError('busy')
        real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'unlink', unlink)
    count, errors = delete_media_files(media, ['chat_1/2026-01-01/busy.jpg', 'chat_1/2026-01-02/free.jpg'])
    assert count == 1
    assert errors == ['chat_1/2026-01-01/busy.jpg: busy']
    assert (media / 'chat_1' / '2026-01-01' / 'busy.jpg').is_file()
    assert not (media / 'chat_1' / '2026-01-02').exists()
