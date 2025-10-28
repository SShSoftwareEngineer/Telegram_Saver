import logging
import shutil
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, send_from_directory, jsonify
from sqlalchemy import delete, select
from configs.config import GlobalConst, MessageFileTypes, ProjectDirs, FormCfg, TagsSorting
from utils import clean_file_path, status_messages
from telegram_handler import tg_handler, TgFile
from database_handler import db_handler, DbDialog, DbMessageGroup, DbFile, DbDialogType, DbFileType

tg_saver = Flask(__name__)


@tg_saver.context_processor
def inject_field_names():
    """
    Регистрация контекстного процессора с именами полей
    """
    return {
        'constants': GlobalConst,
        'tg_file_types': MessageFileTypes,
        'form_ctrl_cfg': FormCfg,
        'tg_me': tg_handler.me,
        'tg_mess_date_from_default': tg_handler.message_sort_filter.date_from_default,
        'tg_dialogs': tg_handler.current_state.dialog_list,
        'tg_messages': tg_handler.current_state.message_group_list,
        'tg_details': tg_handler.current_state.message_details,
        'db_all_dialog_list': db_handler.all_dialogues_list,
        'db_all_tags': db_handler.all_tags_list,
        'db_messages': db_handler.current_state.message_group_list,
        'db_details': db_handler.current_state.message_details,
    }


# Инициализация после создания приложения
with tg_saver.app_context():
    logging.getLogger('werkzeug').setLevel(logging.INFO)


@tg_saver.route(f'/{ProjectDirs.media_dir}/<path:filename>')
def media_dir(filename):
    """
    Регистрация пути для хранения кэшированных изображений.
    Принимает полный путь включая ProjectDirs.media_dir
    """
    return send_from_directory(ProjectDirs.media_dir, filename)


@tg_saver.route('/status_output')
def status_output():
    return jsonify(status_messages.messages)


@tg_saver.route("/")
def index():
    """
    Главная страница приложения
    """
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    chats_count = f'({len(tg_handler.current_state.dialog_list)})' if tg_handler.current_state.dialog_list else ''
    return render_template("index.html", chats_count=chats_count)


@tg_saver.route("/tg_dialogs")
def tg_get_dialogs():
    """
    Получение списка диалогов Telegram
    """
    tg_handler.current_state.dialog_list = tg_handler.get_dialog_list()
    return jsonify({'tg_dialogs': render_template('tg_dialogs.html'),
                    'tg-chats-count': f'({len(tg_handler.current_state.dialog_list)})', })


@tg_saver.route("/tg_messages/<string:dialog_id>")
def tg_get_messages(dialog_id):
    """
    Получение списка сообщений при обновлении текущего диалога
    """
    # Получаем список групп сообщений для выбранного диалога
    tg_message_groups = tg_handler.get_message_group_list(int(dialog_id))
    # Устанавливаем признак сохранения для групп сообщений, которые уже сохранены в базе данных
    for tg_message_group in tg_message_groups:
        tg_message_group.saved_to_db = db_handler.message_group_exists(tg_message_group.grouped_id)
    # Устанавливаем текущее состояние диалога и списка групп сообщений
    tg_handler.current_state.selected_dialog_id = int(dialog_id)
    tg_handler.current_state.message_group_list = tg_message_groups
    return jsonify({'tg_messages': render_template('tg_messages.html'),
                    'tg-messages-count': f'({len(tg_handler.current_state.message_group_list)})',
                    'tg_details': '', })


@tg_saver.route('/tg_details/<string:dialog_id>/<string:message_group_id>')
def tg_get_details(dialog_id: str, message_group_id: str):
    """
    Получение детальной информации о сообщении
    """
    tg_handler.current_state.message_details = (
        tg_handler.get_message_detail(int(dialog_id), message_group_id)) if message_group_id else None
    return jsonify({'tg_details': render_template('tg_details.html')})


@tg_saver.route('/tg_dialog_apply_filters', methods=['POST'])
def tg_dialog_apply_filters():
    """
    Получение списка диалогов Telegram с применением фильтров
    """
    # Установка фильтров диалогов Telegram по значениям из формы
    form_cfg = FormCfg.tg_dialog_filter
    form = request.form
    dial_filter = tg_handler.dialog_sort_filter
    dial_filter.sort_field(form.get(form_cfg['sorting_field']))
    dial_filter.sort_order(form.get(form_cfg['sorting_order']))
    dial_filter.dialog_type(form.get(form_cfg['dialog_type']))
    dial_filter.title_query(form.get(form_cfg['dialog_title_query']))
    # Получение списка диалогов с применением фильтров
    tg_handler.current_state.dialog_list = tg_handler.get_dialog_list()
    # Очистка списка сообщений и деталей сообщений
    tg_handler.current_state.message_group_list = []
    tg_handler.current_state.message_details = None
    return jsonify({'tg_dialogs': render_template('tg_dialogs.html'),
                    'tg-chats-count': f'({len(tg_handler.current_state.dialog_list)})',
                    'tg-messages-count': '', 'tg_messages': '', 'tg_details': '', })


@tg_saver.route('/tg_message_apply_filters', methods=['POST'])
def tg_message_apply_filters():
    """
    Получение списка сообщений диалога Telegram с применением фильтров
    """
    # Установка фильтров списка сообщений Telegram по значениям из формы
    form_cfg = FormCfg.tg_message_filter
    form = request.form
    mess_filter = tg_handler.message_sort_filter
    mess_filter.sort_order = form.get(form_cfg['sorting_order'])
    mess_filter.date_from = form.get(form_cfg['date_from'])
    mess_filter.date_to = form.get(form_cfg['date_to'])
    mess_filter.message_query = form.get(form_cfg['message_query'])
    # Получение списка сообщений с применением фильтров
    tg_handler.current_state.message_group_list = tg_handler.get_message_group_list(
        tg_handler.current_state.selected_dialog_id)
    # Очистка деталей сообщений
    tg_handler.current_state.message_details = None
    return jsonify({'tg_messages': render_template('tg_messages.html'),
                    'tg-messages-count': f'({len(tg_handler.current_state.message_group_list)})',
                    'tg_details': '', })


@tg_saver.route('/tg_save_selected_message_to_db', methods=["POST"])
def tg_save_selected_message_to_db():
    """
    Сохранение отмеченных сообщений в базе данных
    """
    form_cfg = FormCfg.tg_checkbox_list
    selected_messages_ids = request.form.getlist(form_cfg['tg_checkbox_list'])
    selected_messages_ids = [x.replace(GlobalConst.select_in_telegram, '').strip() for x in selected_messages_ids]
    for tg_message_group in tg_handler.current_state.message_group_list:
        if tg_message_group.grouped_id in selected_messages_ids:
            # Если ID группы сообщений находится в списке отмеченных для сохранения, сохраняем её в базе данных.
            if not db_handler.session.in_transaction():
                db_handler.session.begin()
            # Сохраняем или обновляем диалог
            tg_dialog = tg_handler.get_dialog_by_id(tg_message_group.dialog_id)
            db_dialog = db_handler.upsert_record(DbDialog, {'dialog_id': tg_dialog.dialog_id},
                                                 {'title': tg_dialog.title, 'dialog_type_id': tg_dialog.type.value})
            # Устанавливаем relationship для диалога, если не установлен
            if db_dialog.dialog_type is None:
                db_dialog.dialog_type = db_handler.session.query(DbDialogType).filter_by(
                    dialog_type_id=tg_dialog.type.value).first()
            # Сохраняем группу сообщений
            db_message_group = db_handler.upsert_record(DbMessageGroup, {'grouped_id': tg_message_group.grouped_id},
                                                        {'date': tg_message_group.date,
                                                         'text': tg_message_group.text,
                                                         'truncated_text': tg_message_group.truncated_text,
                                                         'files_report': tg_message_group.files_report,
                                                         'from_id': tg_message_group.from_id,
                                                         'dialog_id': tg_dialog.dialog_id})
            # Устанавливаем relationship для группы сообщений, если не установлен
            if db_message_group.dialog is None:
                db_message_group.dialog = db_dialog
            # Сохраняем или обновляем данные о файлах сообщений, входящих в группу.
            status_messages.mess_update('Downloading files', '', new_list=True)
            for tg_file in tg_message_group.files:
                db_file = db_handler.upsert_record(DbFile, {'file_path': tg_file.file_path},
                                                   {'message_id': tg_file.message_id,
                                                    'size': tg_file.size,
                                                    'grouped_id': tg_message_group.grouped_id,
                                                    'file_type_id': tg_file.file_type.type_id})
                # Устанавливаем relationships для файла, если не установлены
                if db_file.message_group is None:
                    db_file.message_group = db_message_group
                if db_file.file_type is None:
                    db_file.file_type = db_handler.session.query(DbFileType).filter_by(
                        file_type_id=tg_file.file_type.type_id).first()
                # Скачиваем файл, если его нет в заданной директории файловой системы и его размер меньше предельного
                status_messages.mess_update('Downloading files', tg_file.file_path)
                downloading_result = tg_handler.download_message_file(tg_file)
                report_msg = f'{tg_file.file_path} downloaded successfully' \
                    if downloading_result else f'Failed to download file {tg_file.file_path}'
                status_messages.mess_update('Downloading files', report_msg)
            db_handler.session.flush()
            # Получаем и сохраняем HTML шаблон с контентом группы сообщений для сохранения в файл.
            message_group_export_data = db_message_group.get_export_data()
            message_group_export_data.update({'files_report': tg_message_group.files_report})
            # Корректируем пути к файлам для возможности открытия из HTML файла в той же директории
            for file in message_group_export_data.get('files', []):
                file['file_name'] = Path(file['file_path']).name
            # Формирование пути к файлу и вложенных директорий в файловой системе
            file_name = TgFile.get_self_file_name(tg_message_group.date, MessageFileTypes.CONTENT,
                                                  tg_message_group.grouped_id, 0, MessageFileTypes.CONTENT.default_ext)
            file_path = Path(
                ProjectDirs.media_dir) / tg_dialog.get_self_dir() / tg_message_group.get_self_dir() / file_name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            # Генерируем HTML контент для файла
            html_content = render_template('export_message.html', **message_group_export_data)
            # Сохраняем HTML файл с контентом сообщения в файловой системе
            with open(file_path, 'w', encoding='utf-8') as cf:
                cf.write(html_content)
            # Создаем запись о HTML файле в базе данных для соответствующей группы сообщений
            db_file = db_handler.upsert_record(DbFile, {'file_path': file_path.as_posix()},
                                               {'message_id': 0,
                                                'size': len(html_content.encode('utf-8')),
                                                'grouped_id': message_group_export_data.get('message_group_id'),
                                                'file_type_id': MessageFileTypes.CONTENT.type_id})
            # Устанавливаем relationships для файла, если не установлены
            if db_file.message_group is None:
                db_file.message_group = db_message_group
            if db_file.file_type is None:
                db_file.file_type = db_handler.session.query(DbFileType).filter_by(
                    file_type_id=MessageFileTypes.CONTENT.type_id).first()
            # Сохраняем изменения в базе данных
            db_handler.session.commit()
            # После сохранения в БД устанавливаем признак "сохранено"
            tg_message_group.saved_to_db = True
            # Обновляем список диалогов, сохраненных в базе данных
            db_handler.all_dialogues_list = db_handler.get_dialog_list()
            db_handler.current_state.dialog_list = db_handler.all_dialogues_list.copy()
            # Устанавливаем признак сохранения для групп сообщений, которые уже сохранены в базе данных
            for tg_message_group in tg_handler.current_state.message_group_list:
                tg_message_group.saved_to_db = db_handler.message_group_exists(tg_message_group.grouped_id)
    # Формирование структуры данных для обновления списков диалогов и сообщений
    data_structure = {'tg_messages': render_template('tg_messages.html'),
                      'tg-messages-count': f'({len(tg_handler.current_state.message_group_list)})',
                      FormCfg.db_message_filter.get(
                          'dialog_select'): db_handler.get_select_content_string(db_handler.current_state.dialog_list,
                                                                                 'dialog_id', 'title')}
    return jsonify(data_structure)


@tg_saver.route('/db_database_maintenance', methods=["POST"])
def db_database_maintenance():
    """
    Сервисное обслуживание базы данных и файловой системы
    1. Удаление из локальной файловой системы файлов, на которые нет ссылок в базе данных
    2. Удаление пустых директорий в локальной файловой системе
    3. Скачивание файлов, на которые есть ссылки в базе данных, но их нет в локальной файловой системе
    4. Резервное копирование базы данных
    5. Удаление неиспользуемых диалогов из таблицы диалогов базы данных
    6. Пересчет количества использований тегов, удаление неиспользуемых из таблицы тегов
    """

    # Получаем из БД все файлы с указанными расширениями
    file_ext_to_sync = [
        MessageFileTypes.IMAGE.default_ext,  # '.jpg'
        MessageFileTypes.VIDEO.default_ext,  # '.mp4'
        MessageFileTypes.CONTENT.default_ext  # '.html'
    ]
    database_files = set([f'{ProjectDirs.media_dir}/{file}' for file in
                          db_handler.get_file_list_by_extension(file_ext_to_sync)])
    # Находим все локальные файлы с указанными расширениями рекурсивно
    local_files = []
    for ext in file_ext_to_sync:
        local_files.extend(Path(ProjectDirs.media_dir).rglob(f'**/*{ext}'))
    local_files = set([x.as_posix() for x in local_files])
    # Сравниваем списки и находим файлы, какие надо удалить и какие нужно докачать
    files_to_delete = local_files - database_files
    files_to_download = database_files - local_files
    # Удаляем файлы, которые есть в локальной файловой системе, но на которые отсутствуют ссылки в базе данных
    files_deleted_count = len([Path(x).unlink() for x in files_to_delete if Path(x).exists()])
    status_messages.mess_update('Synchronizing the list of local files with the database',
                                f'Files deleted from local storage: {files_deleted_count}', True)
    # Удаляем пустые директории
    dir_tree = sorted(Path.walk(Path(ProjectDirs.media_dir)), key=lambda x: len(x[0].as_posix()), reverse=True)
    dir_deleted_count = len([x[0].rmdir() for x in dir_tree if
                             not x[1] and not x[2] and (not x[0].samefile(Path(ProjectDirs.media_dir)))])
    status_messages.mess_update('', f'Empty directories deleted from local storage: {dir_deleted_count}')
    # Скачиваем файлы, которые есть в базе данных, но отсутствуют в локальной файловой системе, кроме HTML файлов
    downloaded_file_list = []
    for file_path in files_to_download:
        # Получаем информацию о файле из базы данных
        downloaded_file = db_handler.get_file_by_local_path(file_path)
        if downloaded_file and Path(file_path).suffix != MessageFileTypes.CONTENT.default_ext:
            downloaded_file_list.append(downloaded_file)
    tg_handler.download_message_file_from_list(downloaded_file_list)
    # Резервное копирование базы данных
    database_backup = (Path(ProjectDirs.data_base_dir) / 'backup' /
                       f'{Path(ProjectDirs.data_base_file).stem}_{datetime.now().strftime("%Y-%m-%d %H_%M_%S")}'
                       f'{Path(ProjectDirs.data_base_file).suffix}')
    # Создаем директории файла, если их нет
    database_backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ProjectDirs.data_base_file, database_backup)
    status_messages.mess_update('', 'Database backup created')
    # Обновление списка диалогов в БД с сортировкой по текущим установкам и удалением неиспользуемых
    db_handler.all_dialogues_list = db_handler.get_dialog_list()
    db_handler.current_state.dialog_list = db_handler.all_dialogues_list.copy()
    # Обновление списка тегов в БД с сортировкой по текущим установкам и пересчетом количества использований
    db_handler.all_tags_list = db_handler.get_all_tag_list()
    # Формирование структуры данных для обновления списков диалогов и тегов в форме базы данных
    data_structure = {FormCfg.db_message_filter.get('dialog_select'): db_handler.get_select_content_string(
        db_handler.current_state.dialog_list, 'dialog_id', 'title'),
        FormCfg.db_detail_tags.get('all_detail_tags'): db_handler.get_select_content_string(
            db_handler.all_tags_list, 'id', 'name')}
    return jsonify(data_structure)


@tg_saver.route('/db_message_apply_filters', methods=['POST'])
def db_message_apply_filters():
    """
    Получение списка сообщений из базы данных с применением фильтров
    """
    # Установка фильтров списка сообщений из базы данных по значениям из формы
    form_cfg = FormCfg.db_message_filter
    form = request.form
    mess_filter = db_handler.message_sort_filter
    mess_filter.selected_dialog_list = form.getlist(form_cfg['dialog_select'])
    mess_filter.sorting_field = form.get(form_cfg['sorting_field'])
    mess_filter.sort_order = form.get(form_cfg['sorting_order'])
    mess_filter.date_from = form.get(form_cfg['date_from'])
    mess_filter.date_to = form.get(form_cfg['date_to'])
    mess_filter.message_query = form.get(form_cfg['message_query'])
    mess_filter.tag_query = form.get(form_cfg['tag_query'])
    # Получение списка сообщений с применением фильтров
    db_handler.current_state.message_group_list = db_handler.get_message_group_list()
    db_handler.current_state.message_details = None
    return jsonify({'db_messages': render_template('db_messages.html'),
                    'db-messages-count': f'({len(db_handler.current_state.message_group_list)})',
                    'db_details': '', })


@tg_saver.route('/db_details/<string:message_group_id>')
def db_get_details(message_group_id: str):
    """
    Получение детальной информации о сообщении из базы данных
    """
    db_handler.current_state.message_details = db_handler.get_message_detail(message_group_id)
    db_handler.current_state.selected_message_group_id = message_group_id
    # Формирование структуры данных для обновления списка тегов
    data_structure = {'db_details': render_template('db_details.html'), FormCfg.db_detail_tags.get(
        'curr_message_tags'): db_handler.get_select_content_string(db_handler.current_state.message_details.get('tags'),
                                                                   'id', 'name')}
    return jsonify(data_structure)


@tg_saver.route('/db_export_selected_message_to_html', methods=["POST"])
def db_export_selected_message_to_html():
    """
    Экспорт отмеченных сообщений из базы данных в HTML файл
    """
    form_cfg = FormCfg.db_checkbox_list
    selected_messages_id = request.form.getlist(form_cfg['db_checkbox_list'])
    export_messages_id = [x.replace(GlobalConst.select_in_database, '').strip() for x in selected_messages_id]
    data_structure = {}
    if export_messages_id:
        status_messages.mess_update(f'Export selected {len(export_messages_id)} messages to HTML file', '',
                                    new_list=True)
        stmt = (select(DbMessageGroup).where(DbMessageGroup.grouped_id.in_(export_messages_id)).order_by(
            DbMessageGroup.date))
        query_result = db_handler.session.execute(stmt).scalars().all()
        exported_messages = []
        export_date_time = clean_file_path(datetime.now().strftime(GlobalConst.message_datetime_format))
        for counter, result in enumerate(query_result, start=1):
            export_data = result.get_export_data()
            # Корректируем пути к файлам для возможности открытия из экспортированного HTML файла
            for file in export_data.get('files', []):
                if Path(Path(ProjectDirs.media_dir) / file.get('file_path')).exists():
                    new_file_path = Path(ProjectDirs.export_dir) / export_date_time / Path(file['file_path']).name
                    new_file_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(Path(ProjectDirs.media_dir) / file.get('file_path'), new_file_path)
                    file['file_path'] = (Path(export_date_time) / Path(file['file_path']).name).as_posix()
            exported_messages.append(export_data)
            status_messages.mess_update('', f'Export message {counter} of {len(export_messages_id)}')
        html_content = render_template('export_multiple_messages.html',
                                       exported_messages=exported_messages,
                                       export_date=datetime.now().strftime(GlobalConst.message_datetime_format))
        with open(Path(ProjectDirs.export_dir) / f'{export_date_time} - {len(exported_messages)} messages.html', 'w',
                  encoding='utf-8') as cf:
            cf.write(html_content)
        status_messages.mess_update('', f'{len(export_messages_id)} messages exported to HTML file')
        # Формирование структуры данных для снятия выделения с экспортированных сообщений
        data_structure = {x: False for x in selected_messages_id}
    return jsonify(data_structure)


@tg_saver.route('/db_delete_selected_from_database', methods=["POST"])
def db_delete_selected_from_database():
    """
    Удаление отмеченных сообщений из базы данных
    """
    form_cfg = FormCfg.db_checkbox_list
    selected_messages_id = request.form.getlist(form_cfg['db_checkbox_list'])
    selected_messages_id = [x.replace(GlobalConst.select_in_database, '').strip() for x in selected_messages_id]
    stmt = delete(DbMessageGroup).where(DbMessageGroup.grouped_id.in_(selected_messages_id))
    db_handler.session.execute(stmt)
    db_handler.session.commit()
    db_handler.current_state.message_group_list = db_handler.get_message_group_list()
    db_handler.current_state.message_details = None
    # Обновляем список диалогов, сохраненных в базе данных
    db_handler.all_dialogues_list = db_handler.get_dialog_list()
    db_handler.current_state.dialog_list = db_handler.all_dialogues_list.copy()
    # Формирование структуры данных для обновления списков диалогов
    data_structure = {'db_messages': render_template('db_messages.html'),
                      'db-messages-count': f'({len(db_handler.current_state.message_group_list)})',
                      'db_details': '',
                      FormCfg.db_message_filter.get(
                          'dialog_select'): db_handler.get_select_content_string(db_handler.current_state.dialog_list,
                                                                                 'dialog_id', 'title')}
    return jsonify(data_structure)


@tg_saver.route('/db_tag_add', methods=['POST'])
def db_tag_add():
    """
    Добавление тега к сообщению
    """
    form_cfg = FormCfg.db_detail_tags
    current_tags_select = all_tags_select = None
    tag_name = request.form.get(form_cfg['edit_tag_name'])
    if tag_name:
        current_tags_select, all_tags_select = (
            db_handler.add_tag_to_message_group(tag_name, db_handler.current_state.selected_message_group_id))
    return jsonify({form_cfg['curr_message_tags']: current_tags_select,
                    form_cfg['all_detail_tags']: all_tags_select})


@tg_saver.route('/db_tag_remove', methods=['POST'])
def db_tag_remove():
    """
    Удаление тега сообщения
    """
    form_cfg = FormCfg.db_detail_tags
    current_tags_select = all_tags_select = None
    tag_name = request.form.get(form_cfg['edit_tag_name'])
    if tag_name:
        current_tags_select, all_tags_select = (
            db_handler.remove_tag_from_message_group(tag_name, db_handler.current_state.selected_message_group_id))
    return jsonify({form_cfg['curr_message_tags']: current_tags_select,
                    form_cfg['all_detail_tags']: all_tags_select})


@tg_saver.route('/db_tag_update', methods=['POST'])
def db_tag_update():
    """
    Изменение тега сообщения
    """
    form_cfg = FormCfg.db_detail_tags
    current_tags_select = all_tags_select = None
    old_tag_name = request.form.get(form_cfg['old_tag_name'])
    new_tag_name = request.form.get(form_cfg['edit_tag_name'])
    if all([old_tag_name, new_tag_name, new_tag_name != old_tag_name]):
        current_tags_select, all_tags_select = (
            db_handler.update_tag_from_message_group(old_tag_name, new_tag_name,
                                                     db_handler.current_state.selected_message_group_id))
    return jsonify({form_cfg['curr_message_tags']: current_tags_select,
                    form_cfg['all_detail_tags']: all_tags_select})


@tg_saver.route('/db_tag_update_everywhere', methods=['POST'])
def db_tag_update_everywhere():
    """
    Изменение тега сообщения и такого же тега всех сообщений
    """
    form_cfg = FormCfg.db_detail_tags
    current_tags_select = all_tags_select = None
    old_tag_name = request.form.get(form_cfg['old_tag_name'])
    new_tag_name = request.form.get(form_cfg['edit_tag_name'])
    if all([old_tag_name, new_tag_name, new_tag_name != old_tag_name]):
        current_tags_select, all_tags_select = (
            db_handler.update_tag_everywhere(old_tag_name, new_tag_name,
                                             db_handler.current_state.selected_message_group_id))
    return jsonify({form_cfg['curr_message_tags']: current_tags_select,
                    form_cfg['all_detail_tags']: all_tags_select})


@tg_saver.route('/db_all_tag_sorting', methods=['POST'])
def db_all_tag_sorting():
    """
    Сортировка всех тегов базы данных в поле выбора тегов
    """
    form_cfg = FormCfg.db_detail_tags
    match request.form.get(form_cfg['tag_sorting_field']):
        case '1':
            db_handler.current_state.all_tags_list_sorting = TagsSorting.USAGE_COUNT_DESC
        case '2':
            db_handler.current_state.all_tags_list_sorting = TagsSorting.UPDATED_AT_DESC
        case _:
            db_handler.current_state.all_tags_list_sorting = TagsSorting.NAME_ASC
    # # Получение списка тегов с сортировкой по текущим установкам
    db_handler.all_tags_list = db_handler.get_all_tag_list()
    return jsonify({form_cfg['all_detail_tags']:
                        db_handler.get_select_content_string(db_handler.all_tags_list, 'id', 'name')})


if __name__ == '__main__':
    tg_saver.run(debug=True, use_reloader=False)

# -*- coding: utf-8 -*-
# TODO: проверить на загрузку разные типы приложений, загрузку видео и аудио, почему возвращает ошибку при Unknown
# TODO: проверить превращение файловой-статусной строки в ссылку в Message_Group
# TODO: Добавить инструкцию по получению своих параметров Телеграм
# TODO: Сделать тесты
# TODO: Оформить READ.ME, код и комментарии по PEP8, PEP257, и прочим рекомендациям
