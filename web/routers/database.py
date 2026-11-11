"""
Database message routes: applying filters, message details, export to HTML, deletion.
Every route is a regular `def` (Starlette runs it in a thread) and holds the global state lock for the whole request.
Маршруты сообщений базы данных: применение фильтров, детали сообщения, экспорт в HTML, удаление.
Каждый роут - обычная `def` (Starlette выполняет ее в потоке) и держит глобальный замок состояния на весь запрос.
"""

import shutil
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from configs.config import FormCfg, GlobalConst, ProjectDirs
from utils import clean_file_path, status_messages
from database_handler import get_db_handler, DbMessageGroup
from web.deps import FormDep, form_list, form_str, render_fragment, state_lock

router = APIRouter()


@router.post('/db_message_apply_filters')
def db_message_apply_filters(request: Request, form: FormDep) -> JSONResponse:
    """
    Getting a list of messages from the database using filters
    Получение списка сообщений из базы данных с применением фильтров
    """
    form_cfg = FormCfg.db_message_filter
    with state_lock:
        db_handler = get_db_handler()
        # Setting filter values for the message list from the database based on values from the form
        # Установка значений фильтра списка сообщений из базы данных по значениям из формы
        mess_filter = db_handler.message_sort_filter
        mess_filter.selected_dialog_list = form_list(form, form_cfg['dialog_select'])  # type: ignore[assignment]
        mess_filter.sorting_field = form_str(form, form_cfg['sorting_field'])
        mess_filter.sort_order = form_str(form, form_cfg['sorting_order'])
        mess_filter.date_from = form_str(form, form_cfg['date_from'])
        mess_filter.date_to = form_str(form, form_cfg['date_to'])
        mess_filter.message_query = form_str(form, form_cfg['message_query'])
        mess_filter.tag_query = form_str(form, form_cfg['tag_query'])
        # Getting list of messages based on filters and sorting
        # Получение списка сообщений с учетом фильтров и сортировки
        db_handler.current_state.message_group_list = db_handler.get_message_group_list()
        db_handler.current_state.message_details = None  # type: ignore[assignment]
        # Updating the message list, message counter, and clearing the message details
        # Обновление списка сообщений, счетчика сообщений и очистка деталей сообщения
        return JSONResponse({'db_messages': render_fragment(request, 'db_messages.html'),
                             'db-messages-count': f'({len(db_handler.current_state.message_group_list)})',
                             'db_details': '', })


@router.get('/db_details/{message_group_id}')
def db_get_details(request: Request, message_group_id: str) -> JSONResponse:
    """
    Getting detailed information about a message from the database
    Получение детальной информации о сообщении из базы данных
    Attributes:
        message_group_id (str): ID of the selected message group / ID выбранной группы сообщений
    """
    with state_lock:
        db_handler = get_db_handler()
        details = db_handler.get_message_detail(message_group_id)
        db_handler.current_state.message_details = details
        db_handler.current_state.selected_message_group_id = message_group_id
        # Creating a data structure for updating the tag list
        # Формирование структуры данных для обновления списка тегов
        return JSONResponse({'db_details': render_fragment(request, 'db_details.html'),
                             FormCfg.db_detail_tags['curr_message_tags']: db_handler.get_select_content_string(
                                 details.get('tags', []), 'id', 'name')})


@router.post('/db_export_selected_message_to_html')
def db_export_selected_message_to_html(  # pylint: disable=too-many-locals
        request: Request, form: FormDep) -> JSONResponse:
    """
    Export marked messages from the database to an HTML file
    Экспорт отмеченных сообщений из базы данных в HTML файл
    """
    # Getting a list of IDs of message groups marked for export from the form
    # Получение из формы списка ID групп сообщений, отмеченных для экспорта
    selected_messages_id = form_list(form, FormCfg.db_checkbox_list['db_checkbox_list'])
    export_messages_id = [x.replace(GlobalConst.select_in_database, '').strip() for x in selected_messages_id]
    data_structure: dict[str, bool] = {}
    if not export_messages_id:
        return JSONResponse(data_structure)
    with state_lock:
        db_handler = get_db_handler()
        # Status bar update / Обновление строки статуса
        status_messages.mess_update(f'Export selected {len(export_messages_id)} messages to HTML file', '',
                                    new_list=True)
        # Querying the database for message groups to be exported (read only, no transaction is needed)
        # Запрос в базу данных групп сообщений, подлежащих экспорту (только чтение, транзакция не нужна)
        stmt = (select(DbMessageGroup).where(DbMessageGroup.grouped_id.in_(export_messages_id))
                .order_by(DbMessageGroup.date))
        query_result = db_handler.session.execute(stmt).scalars().all()
        exported_messages = []
        # Generating a subdirectory name based on the current date and time for exporting files
        # Формирование названия вложенной директории по текущей дате и времени для экспорта файлов
        # (`clean_file_path` returns None only for an empty string, and the date string is never empty)
        # (`clean_file_path` возвращает None только для пустой строки, а строка с датой не бывает пустой)
        export_date_time = clean_file_path(datetime.now().strftime(GlobalConst.message_datetime_format)) or ''
        for counter, result in enumerate(query_result, start=1):
            export_data = result.get_export_data()
            # Correcting file paths so they can be opened from an exported HTML file
            # Коррекция путей к файлам для возможности открытия из экспортированного HTML файла
            for file in export_data.get('files', []):
                if (Path(ProjectDirs.media_dir) / file['file_path']).exists():
                    new_file_path = Path(ProjectDirs.export_dir) / export_date_time / Path(file['file_path']).name
                    new_file_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(Path(ProjectDirs.media_dir) / file['file_path'], new_file_path)
                    file['file_path'] = (Path(export_date_time) / Path(file['file_path']).name).as_posix()
            exported_messages.append(export_data)
            status_messages.mess_update('', f'Export message {counter} of {len(export_messages_id)}')
        # Rendering a page with exported messages and saving it to a file. The export folder is created here too:
        # without copied files nothing else creates it (Flask failed with FileNotFoundError on the first export)
        # Рендеринг страницы с экспортированными сообщениями и сохранение её в файл. Папка экспорта создается и здесь:
        # без скопированных файлов ее больше никто не создает (Flask падал с FileNotFoundError при первом экспорте)
        html_content = render_fragment(request, 'export_multiple_messages.html',
                                       exported_messages=exported_messages,
                                       export_date=datetime.now().strftime(GlobalConst.message_datetime_format))
        export_dir = Path(ProjectDirs.export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)
        with open(export_dir / f'{export_date_time} - {len(exported_messages)} messages.html', 'w',
                  encoding='utf-8') as cf:
            cf.write(html_content)
        # Status bar update / Обновление строки статуса
        status_messages.mess_update('', f'{len(export_messages_id)} messages exported to HTML file')
        # Updating the form to uncheck the exported messages
        # Обновление формы для снятия выделения с экспортированных сообщений
        data_structure = {x: False for x in selected_messages_id}
        return JSONResponse(data_structure)


@router.post('/db_delete_selected_from_database')
def db_delete_selected_from_database(request: Request, form: FormDep) -> JSONResponse:
    """
    Delete marked messages from the database
    Удаление отмеченных сообщений из базы данных
    """
    # Getting a list of IDs of message groups marked for deletion from the form
    # Получение из формы списка ID групп сообщений, отмеченных для удаления
    selected_messages_id = [x.replace(GlobalConst.select_in_database, '').strip()
                            for x in form_list(form, FormCfg.db_checkbox_list['db_checkbox_list'])]
    with state_lock:
        db_handler = get_db_handler()
        # Deleting selected message groups from the database in one transaction. The ORM delete (not a bulk SQL
        # DELETE) also removes the links with tags and the file records; the bulk one fails on the tag links.
        # Удаление отмеченных групп сообщений из базы данных в одной транзакции. Удаление через ORM (а не массовый SQL
        # DELETE) убирает и связи с тегами, и записи о файлах; массовый падает на связях с тегами.
        with db_handler.transaction():
            stmt = select(DbMessageGroup).where(DbMessageGroup.grouped_id.in_(selected_messages_id))
            for message_group in db_handler.session.execute(stmt).scalars().all():
                db_handler.session.delete(message_group)
        # Updating the message list after deletion from the database
        # Обновление списка сообщений после удаления из базы данных
        db_handler.current_state.message_group_list = db_handler.get_message_group_list()
        db_handler.current_state.message_details = None  # type: ignore[assignment]
        # Updating the list of dialogs stored in the database
        # Обновление списка диалогов, сохраненных в базе данных
        db_handler.all_dialogues_list = db_handler.get_dialog_list()
        db_handler.current_state.dialog_list = db_handler.all_dialogues_list.copy()
        # Updating the list of all tags: a tag without messages is removed automatically
        # Обновление списка всех тегов: тег без сообщений удаляется автоматически
        db_handler.all_tags_list = db_handler.get_all_tag_list()
        # Update the list of messages, message counter, message details, tags of the closed message, the dialog filter
        # and the list of all tags / Обновление списка сообщений, счетчика сообщений, деталей сообщения, тегов закрытого
        # сообщения, фильтра диалогов и списка всех тегов
        return JSONResponse({'db_messages': render_fragment(request, 'db_messages.html'),
                             'db-messages-count': f'({len(db_handler.current_state.message_group_list)})',
                             'db_details': '',
                             FormCfg.db_detail_tags['curr_message_tags']: '',
                             FormCfg.db_detail_tags['all_detail_tags']: db_handler.get_select_content_string(
                                 db_handler.all_tags_list, 'id', 'name'),
                             FormCfg.db_message_filter['dialog_select']: db_handler.get_select_content_string(
                                 db_handler.current_state.dialog_list, 'dialog_id', 'title')})
