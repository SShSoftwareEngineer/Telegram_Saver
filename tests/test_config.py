"""
Tests of the configuration: the profile from the environment and the absolute paths of the profile.
Тесты конфигурации: профиль из окружения и абсолютные пути профиля.
"""

import os
import subprocess
import sys
from pathlib import Path
import pytest
import config
from config import BASE_DIR, PROFILE_ENV_VAR, read_profile


def test_profile_not_set_is_empty():
    """Without the variable the profile is not selected / Без переменной профиль не выбран"""
    assert read_profile({}) == ''


@pytest.mark.parametrize('value', ['work', '_dev_1', 'home-2', 'test2'])
def test_profile_from_environment(value: str):
    """The value of the variable is the profile / Значение переменной - это профиль"""
    assert read_profile({PROFILE_ENV_VAR: value}) == value


@pytest.mark.parametrize('value', ['../x', 'a/b', 'a\\b', '.env', 'a b', 'a\n', 'профиль'])
def test_profile_with_unsafe_characters_is_rejected(value: str):
    """The profile is a directory name, so path separators and other characters are refused / Небезопасный профиль"""
    with pytest.raises(ValueError, match=PROFILE_ENV_VAR):
        read_profile({PROFILE_ENV_VAR: value})


def read_paths_in_new_process(cwd: Path, profile: str) -> list[str]:
    """Imports the config in a clean process started in `cwd` and returns the profile and the paths it builds"""
    env = {key: value for key, value in os.environ.items() if key != PROFILE_ENV_VAR}
    env['PYTHONPATH'] = str(BASE_DIR)
    env[PROFILE_ENV_VAR] = profile
    code = ('from config import PROFILE, ProjectDirs as P; '
            'print(PROFILE); print(P.media_dir); print(P.export_dir); print(P.cache_dir); '
            'print(P.telegram_settings_file); print(P.session_file); print(P.data_base_file)')
    result = subprocess.run([sys.executable, '-c', code], cwd=cwd, env=env, capture_output=True, text=True,
                            check=True)
    return result.stdout.splitlines()


def test_paths_are_in_the_profile_directory_and_do_not_depend_on_current_directory(tmp_path: Path):
    """All the data of the profile is in `profiles/<profile name>/`, the paths start from the project root"""
    profile, media, export, cache, settings, session, database = read_paths_in_new_process(tmp_path, 'work')
    profile_dir = BASE_DIR / 'profiles' / 'work'
    assert profile == 'work'
    assert Path(media) == profile_dir / 'media_storage'
    assert Path(export) == profile_dir / 'exported_messages'
    assert Path(cache) == profile_dir / 'cache'
    assert Path(settings) == profile_dir / '.env'
    assert Path(session) == profile_dir / 'telegram'
    assert Path(database) == profile_dir / 'database' / 'telegram_archive.db'


def test_application_refuses_to_start_without_profile(monkeypatch: pytest.MonkeyPatch):
    """No profile selected: an error instead of data created outside `profiles/` / Нет профиля: ошибка"""
    monkeypatch.setattr(config, 'PROFILE', '')
    with pytest.raises(RuntimeError, match=PROFILE_ENV_VAR):
        config.ensure_profile_selected()
