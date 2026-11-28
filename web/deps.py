"""
Shared objects of the web layer: the global state lock, Jinja2 templates, template context and the url_for helper.
Общие объекты веб-слоя: глобальный замок состояния, шаблоны Jinja2, контекст шаблонов и помощник url_for.
"""

from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Annotated, Any
from urllib.parse import quote
from fastapi import Depends, Request
from jinja2 import pass_context
from jinja2.runtime import Context
from markupsafe import Markup
from starlette.datastructures import FormData
from starlette.templating import Jinja2Templates
import config
from config import GlobalConst, MessageFileTypes, FormCfg, ProjectDirs, UnavailableReason
from profiles import profile_title
from telegram_handler import get_tg_handler
from database_handler import get_db_handler
from utils import avatar_color, avatar_initials, find_avatar, format_file_size, format_files_report, to_local

# Project root: templates and static files are looked up relative to it, not to the current directory
# Корень проекта: шаблоны и статические файлы ищем относительно него, а не текущей директории
BASE_DIR = Path(__file__).resolve().parent.parent

# Temporary solution: one lock for the database and the global state (see ROADMAP.md, F18)
# Временное решение: один замок на базу данных и глобальное состояние (см. ROADMAP.md, F18)
state_lock = Lock()


def filter_date(value: datetime | None) -> str:
    """
    Date of a filter for the value of `<input type="date">`: the local day as `YYYY-MM-DD`, or '' if the date is off
    Дата фильтра для значения `<input type="date">`: локальный день в виде `YYYY-MM-DD` или '', если даты нет
    """
    return to_local(value).strftime('%Y-%m-%d') if value else ''


def inject_field_names(_request: Request) -> dict[str, Any]:
    """
    Context processor with field names and the current state (the Flask `inject_field_names` equivalent).
    Контекстный процессор с именами полей и текущим состоянием (аналог Flask `inject_field_names`).
    """
    tg_handler = get_tg_handler()
    db_handler = get_db_handler()
    return {
        'constants': GlobalConst,
        'tg_file_types': MessageFileTypes,
        'unavailable_reasons': UnavailableReason,
        'form_ctrl_cfg': FormCfg,
        'tg_me': tg_handler.me,
        'profile_title': profile_title(config.PROFILE) if config.PROFILE else '',
        'tg_mess_date_from': filter_date(tg_handler.message_sort_filter.date_from),
        'tg_mess_date_to': filter_date(tg_handler.message_sort_filter.date_to),
        'tg_dialogs': tg_handler.current_state.dialog_list,
        'tg_messages': tg_handler.current_state.message_group_list,
        'tg_details': tg_handler.current_state.message_details,
        'db_mess_date_from': filter_date(db_handler.message_sort_filter.date_from),
        'db_mess_date_to': filter_date(db_handler.message_sort_filter.date_to),
        'tg_source_list': tg_handler.current_state.source_chat_list,
        'tg_source_selected': tg_handler.message_sort_filter.selected_source_list or [],
        'db_all_dialog_list': db_handler.all_dialogues_list,
        'db_source_list': db_handler.get_source_list(),
        'db_source_selected': db_handler.message_sort_filter.selected_source_list or [],
        'db_all_tags_select': Markup(db_handler.get_all_tags_select()),
        'db_messages': db_handler.current_state.message_group_list,
        'db_details': db_handler.current_state.message_details,
    }


@pass_context
def url_for(context: Context, endpoint: str, **values: Any) -> str:
    """
    Flask-compatible url_for for Jinja2 templates: `filename` is the `path` of StaticFiles, `_external=True` gives
    an absolute URL, otherwise the URL is relative (as in Flask).
    url_for для шаблонов Jinja2, совместимый с Flask: `filename` - это `path` у StaticFiles, `_external=True` дает
    абсолютный URL, иначе URL относительный (как во Flask).
    """
    request: Request = context['request']
    external = values.pop('_external', False)
    if 'filename' in values:
        values['path'] = values.pop('filename')
    # Path parameters must be strings (dialog IDs come from templates as numbers) and percent-encoded like in Flask
    # (spaces, Cyrillic and '#' in file names); Starlette does not encode them itself
    # Параметры пути должны быть строками (ID диалогов приходят в шаблон числами) и кодироваться как во Flask
    # (пробелы, кириллица и '#' в именах файлов); сам Starlette их не кодирует
    params = {key: quote(str(value), safe="!$&'()*+,/:;=@") for key, value in values.items()}
    if external:
        return str(request.url_for(endpoint, **params))
    return str(request.app.url_path_for(endpoint, **params))


templates = Jinja2Templates(directory=BASE_DIR / 'templates', context_processors=[inject_field_names])
# Replace the built-in Starlette url_for (it always returns absolute URLs)
# Заменяем встроенный url_for Starlette (он всегда возвращает абсолютные URL)
templates.env.globals['url_for'] = url_for


def local_dt(value: datetime, fmt: str) -> str:
    """
    Jinja2 filter: formats a date and time in the local time zone of the system (the dates are stored and passed in
    UTC, the user always sees the local time, as in the Telegram client).
    Фильтр Jinja2: форматирует дату и время в локальном часовом поясе системы (даты хранятся и передаются в UTC,
    пользователь всегда видит локальное время, как в клиенте Telegram).
    """
    return to_local(value).strftime(fmt)


templates.env.filters['local_dt'] = local_dt
templates.env.filters['file_size'] = format_file_size
# The summary line of the files of a message group is formed in the template (it is not stored in the database)
# Строка-резюме файлов группы сообщений формируется в шаблоне (в базе данных она не хранится)
templates.env.globals['format_files_report'] = format_files_report


def avatar_src(dialog_id: int) -> str:
    """
    Jinja2 global: the URL of the avatar of a dialog from the cache, or '' if there is none (the page then shows the
    stub with the initials). The cache is only read: no request to Telegram.
    Глобал Jinja2: URL аватарки диалога из кэша или '', если ее нет (тогда страница показывает заглушку с инициалами).
    Кэш только читается: запроса к Telegram нет.
    """
    relative_path = find_avatar(Path(ProjectDirs.cache_dir), dialog_id)
    return quote(f'/{ProjectDirs.cache_dir_name}/{relative_path}') if relative_path else ''


templates.env.globals.update(avatar_src=avatar_src, avatar_initials=avatar_initials, avatar_color=avatar_color)


def render_fragment(request: Request, name: str, **context: Any) -> str:
    """
    Renders a template to an HTML string (the Flask `render_template` equivalent) for the JSON responses: the page
    scripts put these fragments into the page elements. `TemplateResponse` returns a whole response, not a string, and
    `Template.render` does not call the context processors, so the context is built here. The explicit `context`
    values override the context processor ones (as in Flask).
    Рендерит шаблон в HTML-строку (аналог Flask `render_template`) для JSON-ответов: скрипты страницы вставляют эти
    фрагменты в элементы страницы. `TemplateResponse` возвращает целый ответ, а не строку, а `Template.render` не
    вызывает контекстные процессоры, поэтому контекст собирается здесь. Явно переданные значения `context`
    перекрывают значения контекстного процессора (как во Flask).
    """
    full_context = {'request': request, **inject_field_names(request), **context}
    return templates.get_template(name).render(full_context)


async def read_form(request: Request) -> FormData:
    """
    Reads the submitted form. The field names are dynamic (see `FormCfg`), so `Form(...)` parameters do not fit.
    The dependency is async, so a route that uses it can stay a regular `def` (it runs in a thread).
    Читает отправленную форму. Имена полей динамические (см. `FormCfg`), поэтому параметры `Form(...)` не подходят.
    Зависимость асинхронная, поэтому использующий ее роут может остаться обычным `def` (он выполняется в потоке).
    """
    return await request.form()


FormDep = Annotated[FormData, Depends(read_form)]


def form_str(form: FormData, key: Any) -> Any:
    """
    Value of a text form field, or None if the field is absent (like `request.form.get` in Flask). It is typed `Any`
    on purpose: the `FormCfg` dictionaries mix strings and lists, and the handler methods are annotated `str`
    although they receive None for a missing field, as in Flask.
    Значение текстового поля формы или None, если поля нет (как `request.form.get` во Flask). Тип `Any` намеренный:
    словари `FormCfg` смешивают строки и списки, а методы обработчика аннотированы `str`, хотя получают None для
    отсутствующего поля, как во Flask.
    """
    value = form.get(key)
    return value if isinstance(value, str) else None


def form_list(form: FormData, key: Any) -> list[str]:
    """
    All values of a repeated text form field (like `request.form.getlist` in Flask). Starlette types them as
    `str | UploadFile`; the fields here are text only, so uploaded files are skipped.
    Все значения повторяющегося текстового поля формы (как `request.form.getlist` во Flask). Starlette типизирует их как
    `str | UploadFile`; здесь поля только текстовые, поэтому загруженные файлы пропускаются.
    """
    return [value for value in form.getlist(key) if isinstance(value, str)]
