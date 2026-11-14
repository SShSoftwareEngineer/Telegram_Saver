"""
Telegram routes: reading dialogs, messages and message details, applying filters, saving messages to the database.
Every route is a regular `def` (Starlette runs it in a thread) and holds the global state lock for the whole request.
Маршруты Telegram: чтение диалогов, сообщений и деталей сообщения, применение фильтров, сохранение сообщений в БД.
Каждый роут - обычная `def` (Starlette выполняет ее в потоке) и держит глобальный замок состояния на весь запрос.
"""

from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from configs.config import FormCfg, GlobalConst, MessageFileTypes, ProjectDirs
from utils import status_messages
from telegram_handler import get_tg_handler, TgDialog, TgFile
from database_handler import get_db_handler, DbDialog, DbMessageGroup, DbFile, DbDialogType, DbFileType
from web.deps import FormDep, form_list, form_str, render_fragment, state_lock

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
        # Get a list of message groups for the selected dialogue
        # Получаем список групп сообщений для выбранного диалога
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
        # Обновление списка диалогов и счетчика диалогов, очистка списка сообщений, деталей сообщения
        # и счетчика сообщений
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


@router.post('/tg_save_selected_message_to_db')
def tg_save_selected_message_to_db(request: Request, form: FormDep) -> JSONResponse:
    """
    Saving marked messages in the database
    Сохранение отмеченных сообщений в базе данных
    """
    # Getting a list of IDs of message groups marked for saving from the form
    # Получение из формы списка ID групп сообщений, отмеченных для сохранения
    selected_messages_ids = [x.replace(GlobalConst.select_in_telegram, '').strip()
                             for x in form_list(form, FormCfg.tg_checkbox_list['tg_checkbox_list'])]
    with state_lock:
        tg_handler = get_tg_handler()
        db_handler = get_db_handler()
        message_groups = tg_handler.current_state.message_group_list
        if message_groups is None:
            # No dialog has been opened yet, so there is nothing to save: an empty JSON changes nothing on the page.
            # Flask failed here with a TypeError (500).
            # Диалог еще не открывался, сохранять нечего: пустой JSON ничего не меняет на странице.
            # Во Flask здесь возникала ошибка TypeError (500).
            return JSONResponse({})
        # Processing the list of message groups in the current state of the client
        # Обработка списка групп сообщений в текущего состояния клиента
        for tg_message_group in message_groups:
            if tg_message_group.grouped_id not in selected_messages_ids:
                continue
            # If the message group ID is in the list marked for saving, save it to the database. One transaction per
            # group: an error rolls back only this group, the groups saved before it stay (as in Flask, where
            # `commit` was called for every group). The session starts the transaction itself on the first query.
            # Если ID группы сообщений находится в списке отмеченных для сохранения, сохраняем её в базе данных.
            # Одна транзакция на группу: ошибка откатывает только эту группу, сохраненные ранее остаются (как во Flask,
            # где `commit` вызывался для каждой группы). Транзакцию сессия начинает сама при первом запросе.
            with db_handler.transaction():
                # Save or update the dialog / Сохраняем или обновляем диалог
                tg_dialog: TgDialog = tg_handler.get_dialog_by_id(  # type: ignore[assignment]
                    tg_message_group.dialog_id)
                db_dialog = db_handler.upsert_record(DbDialog, {'dialog_id': tg_dialog.dialog_id},
                                                     {'title': tg_dialog.title,
                                                      'dialog_type_id': tg_dialog.type.value})
                # Set the relationship for the dialog if it is not already set
                # Устанавливаем relationship для диалога, если не установлен
                if db_dialog.dialog_type is None:
                    db_dialog.dialog_type = db_handler.session.query(DbDialogType).filter_by(
                        dialog_type_id=tg_dialog.type.value).first()
                # Saving a group of messages / Сохраняем группу сообщений
                db_message_group = db_handler.upsert_record(DbMessageGroup, {'grouped_id': tg_message_group.grouped_id},
                                                            {'date': tg_message_group.date,
                                                             'text': tg_message_group.text,
                                                             'truncated_text': tg_message_group.truncated_text,
                                                             'files_report': tg_message_group.files_report,
                                                             'sender_id': tg_message_group.sender_id,
                                                             'dialog_id': tg_dialog.dialog_id})
                # Set the relationship for the message group, if not already set
                # Устанавливаем relationship для группы сообщений, если не установлен
                if db_message_group.dialog is None:
                    db_message_group.dialog = db_dialog
                # Save or update data about message files belonging to the group
                # Сохраняем или обновляем данные о файлах сообщений, входящих в группу
                status_messages.mess_update('Downloading files', '', new_list=True)
                for tg_file in tg_message_group.files:
                    db_file = db_handler.upsert_record(DbFile, {'file_path': tg_file.file_path},
                                                       {'message_id': tg_file.message_id,
                                                        'size': tg_file.size,
                                                        'grouped_id': tg_message_group.grouped_id,
                                                        'file_type_id': tg_file.file_type.type_id})
                    # Set relationships for the file, if not already set
                    # Устанавливаем relationships для файла, если не установлено
                    if db_file.message_group is None:
                        db_file.message_group = db_message_group
                    if db_file.file_type is None:
                        db_file.file_type = db_handler.session.query(DbFileType).filter_by(
                            file_type_id=tg_file.file_type.type_id).first()
                    # Download file if it is not in specified directory of the file system and its size is less than
                    # the limit / Скачиваем файл, если его нет в заданной директории файловой системы и его размер
                    # меньше предельного
                    status_messages.mess_update('Downloading files', tg_file.file_path)
                    downloading_result = tg_handler.download_message_file(tg_file)
                    report_msg = f'{tg_file.file_path} downloaded successfully' \
                        if downloading_result else f'Failed to download file {tg_file.file_path}'
                    status_messages.mess_update('Downloading files', report_msg)
                # Not a commit: the group is not saved until the HTML file is written, the rollback is still possible
                # Это не фиксация: группа не сохранена, пока не записан HTML файл, откат еще возможен
                db_handler.session.flush()
                # Get and save the HTML template with the message group content to save to a file
                # Получаем и сохраняем HTML шаблон с контентом группы сообщений для сохранения в файл
                message_group_export_data = db_message_group.get_export_data()
                message_group_export_data.update({'files_report': tg_message_group.files_report})
                # Correcting file paths so that they can be opened from an HTML file in the same directory
                # Корректируем пути к файлам для возможности открытия из HTML файла в той же директории
                for file in message_group_export_data.get('files', []):
                    file['file_name'] = Path(file['file_path']).name
                # Generating paths to files and subdirectories in the file system
                # Формирование пути к файлу и вложенных директорий в файловой системе
                file_name = TgFile.get_self_file_name(tg_message_group.date,  # type: ignore[arg-type]
                                                      MessageFileTypes.CONTENT, tg_message_group.grouped_id, 0,
                                                      MessageFileTypes.CONTENT.default_ext)
                file_path = (Path(ProjectDirs.media_dir) / tg_dialog.get_self_dir() / tg_message_group.get_self_dir()
                             / file_name)
                file_path.parent.mkdir(parents=True, exist_ok=True)
                # Rendering HTML content for a file / Рендеринг HTML контента для файла
                html_content = render_fragment(request, 'export_message.html', **message_group_export_data)
                # Save the HTML file with the message content in the file system
                # Сохраняем HTML файл с контентом сообщения в файловой системе
                with open(file_path, 'w', encoding='utf-8') as cf:
                    cf.write(html_content)
                # Create a record about the HTML file in the database for the corresponding message group. The path is
                # relative to the media directory, like the other files (deletion and maintenance rely on it)
                # Создаем запись о HTML файле в базе данных для соответствующей группы сообщений. Путь относительно
                # директории медиа, как у остальных файлов (на него опираются удаление и сервисное обслуживание)
                relative_path = file_path.relative_to(ProjectDirs.media_dir).as_posix()
                db_file = db_handler.upsert_record(DbFile, {'file_path': relative_path},
                                                   {'message_id': 0,
                                                    'size': len(html_content.encode('utf-8')),
                                                    'grouped_id': message_group_export_data.get('message_group_id'),
                                                    'file_type_id': MessageFileTypes.CONTENT.type_id})
                # Set relationships for the file, if not already set
                # Устанавливаем relationships для файла, если не установлено
                if db_file.message_group is None:
                    db_file.message_group = db_message_group
                if db_file.file_type is None:
                    db_file.file_type = db_handler.session.query(DbFileType).filter_by(
                        file_type_id=MessageFileTypes.CONTENT.type_id).first()
            # The transaction is committed on leaving `with`; after that, set the save flag for the message group
            # Транзакция зафиксирована при выходе из `with`; после этого устанавливаем признак сохранения группы
            tg_message_group.saved_to_db = True
        # Nothing was marked: nothing was saved, so the database lists and the flags stay as they were (as in Flask)
        # Ничего не отмечено: ничего не сохранялось, поэтому списки БД и признаки остаются прежними (как во Flask)
        if selected_messages_ids:
            # Updating the list of dialogs stored in the database
            # Обновляем список диалогов, сохраненных в базе данных
            db_handler.all_dialogues_list = db_handler.get_dialog_list()
            db_handler.current_state.dialog_list = db_handler.all_dialogues_list.copy()
            # Set the save flag for message groups that are already saved in the database (one pass after the loop;
            # in Flask it was nested in the loop over the same list and shadowed the loop variable)
            # Устанавливаем признак сохранения для групп сообщений, которые уже сохранены в базе данных (один проход
            # после цикла; во Flask он был вложен в цикл по тому же списку и перекрывал переменную цикла)
            for tg_message_group in message_groups:
                tg_message_group.saved_to_db = db_handler.message_group_exists(tg_message_group.grouped_id)
        # Update the message list, message counter, and dialogue list in the database dialogue filter
        # Обновление списка сообщений, счетчика сообщений и списка диалогов в фильтре диалогов базы данных
        dialog_select_id = FormCfg.db_message_filter['dialog_select']
        return JSONResponse({'tg_messages': render_fragment(request, 'tg_messages.html'),
                             'tg-messages-count': f'({len(message_groups)})',
                             dialog_select_id: db_handler.get_select_content_string(
                                 db_handler.current_state.dialog_list, 'dialog_id', 'title')})
