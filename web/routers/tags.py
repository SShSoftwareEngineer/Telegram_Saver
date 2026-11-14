"""
Tag routes: adding, removing and renaming the tags of the selected message, renaming a tag everywhere, sorting the list
of all tags. Every route is a regular `def` (Starlette runs it in a thread) and holds the global state lock for the
whole request.
Маршруты тегов: добавление, удаление и изменение тегов выбранного сообщения, изменение тега у всех сообщений,
сортировка списка всех тегов. Каждый роут - обычная `def` (Starlette выполняет ее в потоке) и держит глобальный замок
состояния на весь запрос.
"""

from collections.abc import Callable
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from starlette.datastructures import FormData
from configs.config import FormCfg, TagsSorting
from utils import status_messages
from database_handler import DatabaseHandler, get_db_handler
from web.deps import FormDep, form_str, state_lock

router = APIRouter()

# Signature of the tag methods of DatabaseHandler: (tag names..., message group ID) -> (current tags, all tags)
# Сигнатура методов тегов DatabaseHandler: (имена тегов..., ID группы сообщений) -> (теги сообщения, все теги)
TagMethod = Callable[..., tuple[str | None, str]]


def run_tag_action(form: FormData, method: TagMethod, *, rename: bool) -> JSONResponse:
    """
    The common part of the four tag routes: reads the tag names from the form, checks them and the selected message,
    calls the handler method and builds the response with the tag lists to update. If there is nothing to do, both
    lists are `null` (the page script skips them).
    Общая часть четырех роутов тегов: читает имена тегов из формы, проверяет их и выбранное сообщение, вызывает метод
    обработчика и формирует ответ со списками тегов для обновления. Если делать нечего, оба списка равны `null`
    (скрипт страницы их пропускает).
    Attributes:
        form (FormData): submitted form / отправленная форма
        method (TagMethod): unbound `DatabaseHandler` method / несвязанный метод `DatabaseHandler`
        rename (bool): the method changes a tag (old and new names are needed) / метод меняет тег (нужны два имени)
    """
    form_cfg = FormCfg.db_detail_tags
    edit_tag_name = form_str(form, form_cfg['edit_tag_name'])
    tag_names: tuple[str, ...] = ()
    if rename:
        old_tag_name = form_str(form, form_cfg['old_tag_name'])
        if old_tag_name and edit_tag_name and edit_tag_name != old_tag_name:
            tag_names = (old_tag_name, edit_tag_name)
    elif edit_tag_name:
        tag_names = (edit_tag_name,)
    current_tags_select = all_tags_select = None
    with state_lock:
        db_handler = get_db_handler()
        message_group_id = db_handler.current_state.selected_message_group_id
        if tag_names and not message_group_id:
            # The details are closed, so there is no message to change the tags of
            # Детали закрыты, поэтому нет сообщения, теги которого можно менять
            status_messages.mess_update('Changing message tags', 'No message selected. Select a message first.',
                                        new_list=True)
        elif tag_names:
            # Change the tags of the selected message and get the lists of its tags and of all tags
            # Изменяем теги выбранного сообщения и получаем списки тегов сообщения и всех тегов
            current_tags_select, all_tags_select = method(db_handler, *tag_names, message_group_id)
        # Update the list of tags for the current message and all tags in the database form
        # Обновление списка тегов текущего сообщения и всех тегов в форме базы данных
        return JSONResponse({form_cfg['curr_message_tags']: current_tags_select,
                             form_cfg['all_detail_tags']: all_tags_select})


@router.post('/db_tag_add')
def db_tag_add(form: FormDep) -> JSONResponse:
    """
    Adding a tag to a message
    Добавление тега к сообщению
    """
    return run_tag_action(form, DatabaseHandler.add_tag_to_message_group, rename=False)


@router.post('/db_tag_remove')
def db_tag_remove(form: FormDep) -> JSONResponse:
    """
    Removing a tag from a message
    Удаление тега у сообщения
    """
    return run_tag_action(form, DatabaseHandler.remove_tag_from_message_group, rename=False)


@router.post('/db_tag_update')
def db_tag_update(form: FormDep) -> JSONResponse:
    """
    Changing the tag of the current message
    Изменение тега текущего сообщения
    """
    return run_tag_action(form, DatabaseHandler.update_tag_from_message_group, rename=True)


@router.post('/db_tag_update_everywhere')
def db_tag_update_everywhere(form: FormDep) -> JSONResponse:
    """
    Changing the tag of the current message and the same tag for all messages
    Изменение тега текущего сообщения и такого же тега у всех сообщений
    """
    return run_tag_action(form, DatabaseHandler.update_tag_everywhere, rename=True)


@router.post('/db_tag_all_sorting')
def db_tag_all_sorting(form: FormDep) -> JSONResponse:
    """
    Sorting all database tags in the select all tags field
    Сортировка всех тегов базы данных в поле выбора всех тегов
    """
    form_cfg = FormCfg.db_detail_tags
    with state_lock:
        db_handler = get_db_handler()
        # Setting the sorting method for all tags based on the value from the form
        # Установка метода сортировки для всех тегов по значению из формы
        match form_str(form, form_cfg['tag_sorting_field']):
            case '1':
                db_handler.current_state.all_tags_list_sorting = TagsSorting.USAGE_COUNT_DESC
            case '2':
                db_handler.current_state.all_tags_list_sorting = TagsSorting.UPDATED_AT_DESC
            case _:
                db_handler.current_state.all_tags_list_sorting = TagsSorting.NAME_ASC
        # Get a list of tags sorted by the current sorting method settings
        # Получение списка тегов с сортировкой по текущим установкам метода сортировки
        db_handler.all_tags_list = db_handler.get_all_tag_list()
        # Update the list of all tags in the database form
        # Обновление списка всех тегов в форме базы данных
        return JSONResponse({form_cfg['all_detail_tags']:
                             db_handler.get_select_content_string(db_handler.all_tags_list, 'id', 'name')})
