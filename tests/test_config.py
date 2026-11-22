"""
Tests of the configuration: the profile from the environment and the absolute project paths.
Тесты конфигурации: профиль из окружения и абсолютные пути проекта.
"""

import os
import subprocess
import sys
from pathlib import Path
import pytest
from configs.config import BASE_DIR, PROFILE_ENV_VAR, read_profile


def test_profile_defaults_to_working_one():
    """Without the variable the working profile is used / Без переменной используется рабочий профиль"""
    assert read_profile({}) == ''


@pytest.mark.parametrize('value', ['', '_dev_1', '_dev_2', 'test2'])
def test_profile_from_environment(value: str):
    """The value of the variable is the profile / Значение переменной - это профиль"""
    assert read_profile({PROFILE_ENV_VAR: value}) == value


@pytest.mark.parametrize('value', ['../x', 'a/b', 'a\\b', '.env', 'a b', 'a\n', 'профиль'])
def test_profile_with_unsafe_characters_is_rejected(value: str):
    """The profile goes to file names, so path separators and other characters are refused / Небезопасный профиль"""
    with pytest.raises(ValueError, match=PROFILE_ENV_VAR):
        read_profile({PROFILE_ENV_VAR: value})


def read_paths_in_new_process(cwd: Path, profile: str | None) -> list[str]:
    """Imports the config in a clean process started in `cwd` and returns the profile and the paths it builds"""
    env = {key: value for key, value in os.environ.items() if key != PROFILE_ENV_VAR}
    env['PYTHONPATH'] = str(BASE_DIR)
    if profile is not None:
        env[PROFILE_ENV_VAR] = profile
    code = ('from configs.config import PROFILE, ProjectDirs as P; '
            'print(PROFILE); print(P.media_dir); print(P.export_dir); '
            'print(P.telegram_settings_file); print(P.data_base_file)')
    result = subprocess.run([sys.executable, '-c', code], cwd=cwd, env=env, capture_output=True, text=True,
                            check=True)
    return result.stdout.splitlines()


@pytest.mark.parametrize(('profile', 'suffix'), [(None, ''), ('_dev_1', '_dev_1')])
def test_paths_are_absolute_and_do_not_depend_on_current_directory(tmp_path: Path, profile: str | None, suffix: str):
    """The paths start from the project root whatever the current directory is, the profile sets two file names"""
    media, export, settings, database = read_paths_in_new_process(tmp_path, profile)[1:]
    assert Path(media) == BASE_DIR / 'media_storage'
    assert Path(export) == BASE_DIR / 'exported_messages'
    assert Path(settings) == BASE_DIR / 'configs' / f'.env{suffix}'
    assert Path(database) == BASE_DIR / 'database' / f'telegram_archive{suffix}.db'
