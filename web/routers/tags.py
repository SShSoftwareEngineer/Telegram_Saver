"""
Tag routes: adding, removing and renaming the tags of the checked messages, renaming a tag in all messages, sorting the
list of all tags. The tag buttons act on the messages checked in the list of the database tab (not on the message open
in the details); the open message only gets its tag field refreshed. Every route is a regular `def` (Starlette runs it
in a thread) and holds the global state lock for the whole request.
Маршруты тегов: добавление, удаление и изменение тегов отмеченных сообщений, изменение тега у всех сообщений,
сортировка списка всех тегов. Кнопки тегов действуют на сообщения, отмеченные в списке вкладки БД (а не на сообщение,
открытое в деталях); открытому сообщению только обновляется поле тегов. Каждый роут - обычная `def` (Starlette
выполняет ее в потоке) и держит глобальный замок состояния на весь запрос.
"""

from collections.abc import Callable
from fastapi import APIRouter
from starlette.datastructures import FormData
from config import FormCfg, GlobalConst, TagsSorting
from utils import status_messages
from database_handler import DatabaseHandler, TagChange, get_db_handler, is_no_tags_name
from web.deps import FormDep, form_list, form_str, state_lock
from web.ui import ui_update

router = APIRouter()

# A tag method of DatabaseHandler: (handler, tag names..., [checked message IDs,] open message ID) -> TagChange
# Метод тегов DatabaseHandler: (обработчик, имена тегов..., [ID отмеченных сообщений,] ID открытого сообщения)
TagMethod = Callable[..., TagChange]

NO_MESSAGES_CHECKED = 'No messages checked. Check the messages first.'
RESERVED_TAG_NAME = f'"{GlobalConst.no_tags_name}" is a reserved name: it is not a tag and cannot be added or changed.'


def message_group_id(checkbox_value: str) -> str:
    """
    ID of a message group from the value of its checkbox (the value carries a prefix, like in the export)
    ID группы сообщений из значения ее чек-бокса (значение несет префикс, как при экспорте)
    """
    return checkbox_value.replace(GlobalConst.select_in_database, '').strip()


def run_tag_action(form: FormData, method: TagMethod, *, rename: bool, report: str,
                   everywhere: bool = False) -> JSONResponse:
    """
    The common part of the four tag routes: reads the tag names and the checked messages from the form, calls the
    handler method, writes the result to the status bar and builds the response with the tag lists to update. When the
    operation on the checked messages is done, their checkboxes are unchecked (the response sets them to `False`, like
    after the export). If there is nothing to do (no tag name, or no checked messages), the response has no tag lists
    (an empty one, see `web/ui.py`) and the checkboxes stay as they are.
    Общая часть четырех роутов тегов: читает имена тегов и отмеченные сообщения из формы, вызывает метод обработчика,
    пишет результат в строку статуса и формирует ответ со списками тегов для обновления. Когда операция над
    отмеченными сообщениями выполнена, с их чек-боксов снимаются галочки (ответ задает им `False`, как после
    экспорта). Если делать нечего (нет имени тега или нет отмеченных сообщений), в ответе нет списков тегов (он
    пустой, см. `web/ui.py`), а галочки остаются как есть.
    Attributes:
        form (FormData): submitted form / отправленная форма
        method (TagMethod): unbound `DatabaseHandler` method / несвязанный метод `DatabaseHandler`
        rename (bool): the method changes a tag (old and new names are needed) / метод меняет тег (нужны два имени)
        report (str): the status text; `{tag}` is the (old) tag name, `{new}` the new one, `{changed}` the number of
            changed messages, `{total}` the number of checked messages / текст статуса
        everywhere (bool): the method does not depend on the checked messages / метод не зависит от отмеченных сообщений
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
    checked_values = form_list(form, FormCfg.db_checkbox_list['db_checkbox_list'])
    checked_ids = [message_group_id(value) for value in checked_values]
    current_tags_select = all_tags_select = None
    unchecked: dict[str, bool] = {}
    with state_lock:
        db_handler = get_db_handler()
        # The open message is not the target of the action: it only gets its tag field refreshed if it is affected
        # Открытое сообщение не цель действия: ему только обновляется поле тегов, если оно затронуто
        open_message_id = db_handler.current_state.selected_message_group_id
        if any(is_no_tags_name(name) for name in tag_names):
            # "(No tags)" is only an item of the tag filter, not a tag: nothing can be done with it
            # «(No tags)» - только пункт фильтра по тегам, а не тег: с ним ничего делать нельзя
            status_messages.mess_update('Changing message tags', RESERVED_TAG_NAME, new_list=True)
        elif tag_names and not everywhere and not checked_ids:
            status_messages.mess_update('Changing message tags', NO_MESSAGES_CHECKED, new_list=True)
        elif tag_names:
            # One transaction for all the checked messages; get the lists of the open message tags and of all tags
            # Одна транзакция на все отмеченные сообщения; получаем списки тегов открытого сообщения и всех тегов
            arguments = (*tag_names, open_message_id) if everywhere else (*tag_names, checked_ids, open_message_id)
            change = method(db_handler, *arguments)
            status_messages.mess_update('Changing message tags', report.format(
                tag=tag_names[0], new=tag_names[-1], changed=change.changed, total=len(checked_ids)), new_list=True)
            current_tags_select, all_tags_select = change.current_tags_select, change.all_tags_select
            if not everywhere:
                # The operation is over: uncheck the messages it was done on (the keys are the checkbox IDs)
                # Операция закончена: снимаем галочки с сообщений, над которыми она выполнена (ключи - ID чек-боксов)
                unchecked = {value: False for value in checked_values}
        # Update the list of tags for the open message and all tags in the database form, uncheck the messages
        # Обновление списка тегов открытого сообщения и всех тегов в форме базы данных, снятие галочек с сообщений
        return ui_update({form_cfg['curr_message_tags']: current_tags_select,
                          form_cfg['all_detail_tags']: all_tags_select}, unchecked)


@router.post('/db_tag_add')
def db_tag_add(form: FormDep) -> JSONResponse:
    """
    Adding a tag to the checked messages
    Добавление тега к отмеченным сообщениям
    """
    return run_tag_action(form, DatabaseHandler.add_tag_to_message_groups, rename=False,
                          report='Tag "{tag}" added to {changed} of {total} checked messages')


@router.post('/db_tag_remove')
def db_tag_remove(form: FormDep) -> JSONResponse:
    """
    Removing a tag from the checked messages
    Удаление тега у отмеченных сообщений
    """
    return run_tag_action(form, DatabaseHandler.remove_tag_from_message_groups, rename=False,
                          report='Tag "{tag}" removed from {changed} of {total} checked messages')


@router.post('/db_tag_update')
def db_tag_update(form: FormDep) -> JSONResponse:
    """
    Changing the tag of the checked messages that have it
    Изменение тега у отмеченных сообщений, где он есть
    """
    return run_tag_action(form, DatabaseHandler.update_tag_from_message_groups, rename=True,
                          report='Tag "{tag}" changed to "{new}" in {changed} of {total} checked messages')


@router.post('/db_tag_update_everywhere')
def db_tag_update_everywhere(form: FormDep) -> JSONResponse:
    """
    Changing the tag in all messages that have it (the checked messages do not matter)
    Изменение тега у всех сообщений, где он есть (отмеченные сообщения не важны)
    """
    return run_tag_action(form, DatabaseHandler.update_tag_everywhere, rename=True, everywhere=True,
                          report='Tag "{tag}" renamed to "{new}" in {changed} messages')


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
                db_handler.current_state.all_tags_list_sorting = TagsSorting.CREATED_AT_DESC
            case _:
                db_handler.current_state.all_tags_list_sorting = TagsSorting.NAME_ASC
        # Get a list of tags sorted by the current sorting method settings
        # Получение списка тегов с сортировкой по текущим установкам метода сортировки
        db_handler.all_tags_list = db_handler.get_all_tag_list()
        # Update the list of all tags in the database form
        # Обновление списка всех тегов в форме базы данных
        return ui_update({form_cfg['all_detail_tags']: db_handler.get_all_tags_select()})
