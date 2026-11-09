"""
Telegram routes: reading dialogs, messages and message details, applying filters. Every route is a regular `def`
(Starlette runs it in a thread) and holds the global state lock for the whole request.
Маршруты Telegram: чтение диалогов, сообщений и деталей сообщения, применение фильтров. Каждый роут - обычная `def`
(Starlette выполняет ее в потоке) и держит глобальный замок состояния на весь запрос.
"""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from configs.config import FormCfg
from telegram_handler import get_tg_handler
from database_handler import get_db_handler
from web.deps import FormDep, form_str, render_fragment, state_lock

router = APIRouter()


@router.get('/tg_dialogs')
def tg_get_dialogs(request: Request) -> JSONResponse:
    """
    Getting a list of Telegram dialogs
    Получение списка диалогов Telegram
    """
    with state_lock:
        tg_handler = get_tg_handler()
        tg_handler.current_state.dialog_list = tg_handler.get_dialog_list()
        # Updating the list of dialogs and the dialog count counter
        # Обновление списка диалогов и счетчика количества диалогов
        return JSONResponse({'tg_dialogs': render_fragment(request, 'tg_dialogs.html'),
                             'tg-chats-count': f'({len(tg_handler.current_state.dialog_list)})', })


@router.get('/tg_messages/{dialog_id}')
def tg_get_messages(request: Request, dialog_id: int) -> JSONResponse:
    """
    Getting a list of messages when the current dialog changes
    Получение списка сообщений при изменении текущего диалога
    Attributes:
        dialog_id (int): ID of the selected dialog (negative for groups and channels) /
            ID выбранного диалога (отрицательный у групп и каналов)
    """
    with state_lock:
        tg_handler = get_tg_handler()
        db_handler = get_db_handler()
        # Get a list of message groups for the selected dialogue / Получаем список групп сообщений для выбранного диалога
        tg_message_groups = tg_handler.get_message_group_list(dialog_id)
        # Check which message groups are already saved in the database
        # Проверяем, какие группы сообщений уже сохранены в базе данных
        for tg_message_group in tg_message_groups:
            tg_message_group.saved_to_db = db_handler.message_group_exists(tg_message_group.grouped_id)
        # Set the Telegram ID of the current dialogue and the list of message groups in the current state of the client
        # Устанавливаем в текущем состоянии клиента Telegram ID текущего диалога и список групп сообщений
        tg_handler.current_state.selected_dialog_id = dialog_id
        tg_handler.current_state.message_group_list = tg_message_groups
        # Refresh message list, message counter, and clear current message details
        # Обновление списка сообщений, счетчика сообщений и очистка деталей текущего сообщения
        return JSONResponse({'tg_messages': render_fragment(request, 'tg_messages.html'),
                             'tg-messages-count': f'({len(tg_handler.current_state.message_group_list)})',
                             'tg_details': '', })


@router.get('/tg_details/{dialog_id}/{message_group_id}')
def tg_get_details(request: Request, dialog_id: int, message_group_id: str) -> JSONResponse:
    """
    Getting detailed information from a Telegram message
    Получение детальной информации сообщения Telegram
    Attributes:
        dialog_id (int): ID of the selected dialog / ID выбранного диалога
        message_group_id (str): ID of the selected message group / ID выбранной группы сообщений
    """
    with state_lock:
        tg_handler = get_tg_handler()
        tg_handler.current_state.message_details = tg_handler.get_message_detail(dialog_id, message_group_id)
        # Updating message details / Обновление деталей сообщения
        return JSONResponse({'tg_details': render_fragment(request, 'tg_details.html')})


@router.post('/tg_dialog_apply_filters')
def tg_dialog_apply_filters(request: Request, form: FormDep) -> JSONResponse:
    """
    Getting a list of Telegram chats using filters
    Получение списка диалогов Telegram с применением фильтров
    """
    form_cfg = FormCfg.tg_dialog_filter
    with state_lock:
        tg_handler = get_tg_handler()
        # Setting Telegram dialog filter values based on values from the form
        # Установка значений фильтров диалогов Telegram по значениям из формы
        dial_filter = tg_handler.dialog_sort_filter
        dial_filter.sort_field(form_str(form, form_cfg['sorting_field']))
        dial_filter.sort_order(form_str(form, form_cfg['sorting_order']))
        dial_filter.dialog_type(form_str(form, form_cfg['dialog_type']))
        dial_filter.title_query(form_str(form, form_cfg['dialog_title_query']))
        # Getting a list of dialogs using filters / Получение списка диалогов с применением фильтров
        tg_handler.current_state.dialog_list = tg_handler.get_dialog_list()
        # Clearing the message list and message details in the current state of the client
        # Очистка списка сообщений и деталей сообщений в текущем состоянии клиента
        tg_handler.current_state.message_group_list = []
        tg_handler.current_state.message_details = None
        # Update list of dialogs and the dialog counter, clear list of messages, message details, and message counter
        # Обновление списка диалогов и счетчика диалогов, очистка списка сообщений, деталей сообщения и счетчика сообщений
        return JSONResponse({'tg_dialogs': render_fragment(request, 'tg_dialogs.html'),
                             'tg-chats-count': f'({len(tg_handler.current_state.dialog_list)})',
                             'tg-messages-count': '', 'tg_messages': '', 'tg_details': '', })


@router.post('/tg_message_apply_filters')
def tg_message_apply_filters(request: Request, form: FormDep) -> JSONResponse:
    """
    Getting a list of messages from the current Telegram chat using filters
    Получение списка сообщений текущего диалога Telegram с применением фильтров
    """
    form_cfg = FormCfg.tg_message_filter
    with state_lock:
        tg_handler = get_tg_handler()
        # Setting current dialog Telegram message list filter values based on values from the form
        # Установка значений фильтров списка сообщений текущего диалога Telegram по значениям из формы
        mess_filter = tg_handler.message_sort_filter
        mess_filter.sort_order = form_str(form, form_cfg['sorting_order'])
        mess_filter.date_from = form_str(form, form_cfg['date_from'])
        mess_filter.date_to = form_str(form, form_cfg['date_to'])
        mess_filter.message_query = form_str(form, form_cfg['message_query'])
        # Getting a list of messages using filters / Получение списка сообщений с применением фильтров
        tg_handler.current_state.message_group_list = tg_handler.get_message_group_list(
            tg_handler.current_state.selected_dialog_id)  # type: ignore[arg-type]
        # Clearing the message details window / Очистка окна деталей сообщения
        tg_handler.current_state.message_details = None
        # Updating the message list, message counter, and clearing the message details
        # Обновление списка сообщений, счетчика сообщений и очистка деталей сообщения
        return JSONResponse({'tg_messages': render_fragment(request, 'tg_messages.html'),
                             'tg-messages-count': f'({len(tg_handler.current_state.message_group_list)})',
                             'tg_details': '', })
