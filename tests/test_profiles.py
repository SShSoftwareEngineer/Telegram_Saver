"""
Tests of the profiles: the list, the creation, the choice at the start and `profile.json`.
Тесты профилей: список, создание, выбор при запуске и `profile.json`.
"""

from pathlib import Path
import pytest
import profiles
from profiles import (PROFILE_ENV_VAR, choose_profile, create_profile, list_profiles, profile_title, read_profile_info,
                      write_profile_info)


@pytest.fixture
def profiles_dir(tmp_path: Path) -> Path:
    """Directory with profiles / Каталог профилей"""
    directory = tmp_path / 'profiles'
    directory.mkdir()
    return directory


@pytest.fixture
def template(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The settings template that `create_profile` copies / Шаблон настроек, который копирует `create_profile`"""
    path = tmp_path / '.env.example'
    path.write_text('PHONE=x\n', encoding='utf-8')
    monkeypatch.setattr(profiles, 'SETTINGS_TEMPLATE', path)
    return path


class Answers:
    """Scripted answers of the user and the collected output / Заданные ответы пользователя и собранный вывод"""

    def __init__(self, *answers: str):
        self.answers = list(answers)
        self.output: list[str] = []

    def ask(self, _prompt: str) -> str:
        return self.answers.pop(0)

    def tell(self, text: str) -> None:
        self.output.append(text)


def test_list_is_alphabetical_and_skips_files_and_bad_names(profiles_dir: Path):
    """Only the subdirectories with a valid name are profiles, case-insensitive alphabetical order"""
    for name in ('work', 'Home', 'a-1', 'bad name', '.hidden'):
        (profiles_dir / name).mkdir()
    (profiles_dir / 'file.txt').write_text('', encoding='utf-8')
    assert list_profiles(profiles_dir) == ['a-1', 'Home', 'work']


def test_list_without_directory_is_empty(tmp_path: Path):
    assert list_profiles(tmp_path / 'missing') == []


def test_create_copies_the_template(profiles_dir: Path, template: Path):
    directory = create_profile('work', profiles_dir, template)
    assert (directory / '.env').read_text(encoding='utf-8') == 'PHONE=x\n'
    for subdir in ('database/backup', 'media_storage', 'exported_messages', 'cache'):
        assert (directory / subdir).is_dir(), subdir
    with pytest.raises(FileExistsError):
        create_profile('work', profiles_dir, template)
    with pytest.raises(ValueError):
        create_profile('../x', profiles_dir, template)


def test_argument_has_priority_over_the_variable(profiles_dir: Path):
    for name in ('a', 'b', 'c'):
        (profiles_dir / name).mkdir()
    assert choose_profile(['--profile', 'b'], {PROFILE_ENV_VAR: 'c'}, profiles_dir) == 'b'
    assert choose_profile(['--profile=a'], {}, profiles_dir) == 'a'
    assert choose_profile([], {PROFILE_ENV_VAR: 'c'}, profiles_dir) == 'c'


def test_unknown_profile_is_refused(profiles_dir: Path):
    (profiles_dir / 'a').mkdir()
    with pytest.raises(SystemExit):
        choose_profile(['--profile', 'zzz'], {}, profiles_dir)
    with pytest.raises(SystemExit):
        choose_profile(['--profile'], {}, profiles_dir)


def test_the_only_profile_is_taken_without_questions(profiles_dir: Path):
    (profiles_dir / 'work').mkdir()
    assert choose_profile([], {}, profiles_dir, ask=lambda _: pytest.fail('no question expected')) == 'work'


def test_menu_shows_account_names_and_takes_the_number(profiles_dir: Path):
    for name in ('b', 'a'):
        (profiles_dir / name).mkdir()
    write_profile_info(profiles_dir / 'b', 7, 'Ivan Ivanov')
    answers = Answers('x', '2')
    assert choose_profile([], {}, profiles_dir, answers.ask, answers.tell) == 'b'
    assert '  1. a' in answers.output
    assert '  2. b (Ivan Ivanov)' in answers.output
    assert 'Wrong choice / Неверный выбор' in answers.output


def test_menu_creates_a_new_profile_and_exits(profiles_dir: Path, template: Path):
    for name in ('a', 'b'):
        (profiles_dir / name).mkdir()
    answers = Answers('0', 'a', 'new-one')
    with pytest.raises(SystemExit) as stop:
        choose_profile([], {}, profiles_dir, answers.ask, answers.tell)
    assert stop.value.code == 0
    assert (profiles_dir / 'new-one' / '.env').exists()
    assert any('already exists' in line for line in answers.output)


def test_no_profiles_offers_to_create_one(profiles_dir: Path, template: Path):
    answers = Answers('first')
    with pytest.raises(SystemExit):
        choose_profile([], {}, profiles_dir, answers.ask, answers.tell)
    assert (profiles_dir / 'first' / '.env').exists()


def test_empty_name_cancels_the_creation(profiles_dir: Path, template: Path):
    answers = Answers('')
    with pytest.raises(SystemExit) as stop:
        choose_profile([], {}, profiles_dir, answers.ask, answers.tell)
    assert stop.value.code != 0
    assert list_profiles(profiles_dir) == []


def test_profile_info_roundtrip(tmp_path: Path):
    assert read_profile_info(tmp_path) == {}
    write_profile_info(tmp_path, 42, 'Иван')
    assert read_profile_info(tmp_path) == {'user_id': 42, 'name': 'Иван'}
    (tmp_path / 'profile.json').write_text('{broken', encoding='utf-8')
    assert read_profile_info(tmp_path) == {}
    assert profile_title('x', tmp_path.parent) == 'x'


def test_account_of_the_profile_is_checked(work_dir: Path):
    """The first login writes the account to `profile.json`, another account is refused later"""
    from types import SimpleNamespace
    from telegram_handler import TelegramHandler
    check = TelegramHandler._check_profile_account  # pylint: disable=protected-access
    me = SimpleNamespace(id=5, first_name='Ivan', last_name='Ivanov', username='iv')
    check(SimpleNamespace(me=me))
    assert read_profile_info(work_dir) == {'user_id': 5, 'name': 'Ivan Ivanov'}
    me.first_name = 'Petr'  # The name is refreshed, the ID is the same / Имя обновляется, ID тот же
    check(SimpleNamespace(me=me))
    assert read_profile_info(work_dir)['name'] == 'Petr Ivanov'
    with pytest.raises(RuntimeError, match='profile belongs'):
        check(SimpleNamespace(me=SimpleNamespace(id=6, first_name='X', last_name=None, username=None)))


def test_failed_creation_leaves_no_directory(profiles_dir: Path, tmp_path: Path):
    """No template: the half-made directory is removed, so the name stays free / Нет шаблона: каталог удаляется"""
    with pytest.raises(OSError):
        create_profile('work', profiles_dir, tmp_path / 'missing.example')
    assert not (profiles_dir / 'work').exists()


def test_menu_reports_a_creation_error(profiles_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """An OS error while creating the profile ends the start with a message, not with a traceback"""
    monkeypatch.setattr(profiles, 'SETTINGS_TEMPLATE', tmp_path / 'missing.example')
    monkeypatch.setattr(profiles.create_profile, '__defaults__', (profiles_dir, tmp_path / 'missing.example'))
    with pytest.raises(SystemExit, match='Could not create'):
        profiles.choose_profile([], {}, profiles_dir, Answers('work').ask, Answers().tell)
    assert not (profiles_dir / 'work').exists()
