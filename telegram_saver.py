import logging
from pathlib import Path
from typing import Optional
from flask import Flask, render_template, request, send_from_directory, jsonify

from configs.config import GlobalConst, MessageFileTypes, ProjectDirs, FormButtonCfg, TagsSorting, status_messages
from telegram_handler import TelegramHandler, TgFile
from database_handler import DatabaseHandler, DbDialog, DbMessageGroup, DbFile, DbDialogType, DbFileType

tg_saver = Flask(__name__)
tg_handler = TelegramHandler()
db_handler = DatabaseHandler()


@tg_saver.context_processor
def inject_field_names():
    """
    Регистрация контекстного процессора с именами полей
    """
    return {
        'constants': GlobalConst,
        'tg_file_types': MessageFileTypes,
        'form_btn_cfg': FormButtonCfg,
        'tg_mess_date_from_default': tg_handler.message_sort_filter.date_from_default,
        'tg_dialogs': tg_handler.current_state.dialog_list,
        'tg_messages': tg_handler.current_state.message_group_list,
        'tg_details': tg_handler.current_state.message_details,
        'db_all_dialog_list': db_handler.all_dialogues_list,
        'db_all_tags': db_handler.all_tags_list,
        'db_messages': db_handler.current_state.message_group_list,
        'db_details': db_handler.current_state.message_details,
    }


def initialize_data():
    """
    Инициализация данных при запуске
    """
    logging.getLogger('werkzeug').setLevel(logging.INFO)


# Инициализация после создания приложения
with tg_saver.app_context():
    initialize_data()


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
    tg_handler.current_state.message_details = tg_handler.get_message_detail(int(dialog_id),
                                                                             message_group_id) if message_group_id else None
    return jsonify({'tg_details': render_template('tg_details.html')})


@tg_saver.route('/tg_dialog_apply_filters', methods=['POST'])
def tg_dialog_apply_filters():
    """
    Получение списка диалогов Telegram с применением фильтров
    """
    # Установка фильтров диалогов Telegram по значениям из формы
    form_cfg = FormButtonCfg.tg_dialog_filter
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
    form_cfg = FormButtonCfg.tg_message_filter
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


def get_dict_value_by_partial_key(my_dict: dict, key_part: str) -> Optional[str]:
    """
    Получает значение из словаря по части ключа
    """
    for key, value in my_dict.items():
        if key_part in key:
            return value
    return None


@tg_saver.route('/tg_select_messages', methods=["POST"])
def tg_select_messages():
    """
    Обработка отметки сохранения сообщений Telegram в списке сообщений
    """
    # Получаем id группы сообщений
    selected_message_group_id = get_dict_value_by_partial_key(request.form, GlobalConst.mess_group_id)
    # Получаем значение признака сохранения (чекбокса) для группы сообщений
    is_selected = get_dict_value_by_partial_key(request.form, GlobalConst.select_to_save) is not None
    # Устанавливаем признак сохранения для выбранной группы сообщений
    if selected_message_group_id:
        tg_handler.get_message_group_by_id(tg_handler.current_state.message_group_list,
                                           selected_message_group_id).selected = is_selected
    return jsonify({})


@tg_saver.route('/tg_select_details', methods=["POST"])
def tg_select_details():
    """
    Обработка отметки сохранения сообщений в базе данных в деталях сообщения
    """
    # Получаем id группы сообщений
    selected_message_group_id = get_dict_value_by_partial_key(request.form, GlobalConst.mess_group_id)
    # Получаем значение признака сохранения (чекбокса) для группы сообщений
    is_selected = get_dict_value_by_partial_key(request.form, GlobalConst.select_to_save) is not None
    # Устанавливаем признак сохранения для выбранной группы сообщений
    if selected_message_group_id:
        tg_handler.get_message_group_by_id(tg_handler.current_state.message_group_list,
                                           selected_message_group_id).selected = is_selected
    return jsonify({})


@tg_saver.route('/save_selected_message_to_db', methods=["POST"])
def save_selected_message_to_db():
    """
    Сохранение отмеченных сообщений в базе данных
    """
    for tg_message_group in tg_handler.current_state.message_group_list:
        if tg_message_group.selected:
            # Если группа сообщений отмечена для сохранения, сохраняем её в базе данных.
            # Сохраняем или обновляем диалог
            tg_dialog = tg_handler.get_dialog_by_id(tg_message_group.dialog_id)
            db_dialog = db_handler.upsert_record(DbDialog, dict(dialog_id=tg_dialog.dialog_id),
                                                 dict(title=tg_dialog.title,
                                                      dialog_type_id=tg_dialog.type.value))
            # Устанавливаем relationship для диалога, если не установлен
            if db_dialog.dialog_type is None:
                db_dialog.dialog_type = db_handler.session.query(DbDialogType).filter_by(
                    dialog_type_id=tg_dialog.type.value).first()
            # Сохраняем группу сообщений
            db_message_group = db_handler.upsert_record(DbMessageGroup, dict(grouped_id=tg_message_group.grouped_id),
                                                        dict(date=tg_message_group.date,
                                                             text=tg_message_group.text,
                                                             truncated_text=tg_message_group.truncated_text,
                                                             files_report=tg_message_group.files_report,
                                                             from_id=tg_message_group.from_id,
                                                             reply_to=tg_message_group.reply_to,
                                                             dialog_id=tg_dialog.dialog_id))
            # Устанавливаем relationship для группы сообщений, если не установлен
            if db_message_group.dialog is None:
                db_message_group.dialog = db_dialog
            # Сохраняем или обновляем данные о файлах сообщений, входящих в группу
            status_messages.mess_update('Downloading files', '', new_list=True)
            for tg_file in tg_message_group.files:
                db_file = db_handler.upsert_record(DbFile, dict(file_path=tg_file.file_path),
                                                   dict(message_id=tg_file.message_id,
                                                        size=tg_file.size,
                                                        grouped_id=tg_message_group.grouped_id,
                                                        file_type_id=tg_file.file_type.type_id))
                # Устанавливаем relationships для файла, если не установлены
                if db_file.message_group is None:
                    db_file.message_group = db_message_group
                if db_file.file_type is None:
                    db_file.file_type = db_handler.session.query(DbFileType).filter_by(
                        file_type_id=tg_file.file_type.type_id).first()
                # Скачиваем файл, если его нет в заданной директории файловой системы и его размер меньше предельного
                status_messages.mess_update('Downloading files', tg_file.file_path)
                downloading_result = tg_handler.download_message_file(tg_file)
                report_msg = f'{tg_file.file_path} downloaded successfully' if downloading_result else f'Failed to download file {tg_file.file_path}'
                status_messages.mess_update('Downloading files', report_msg)
            # Сохраняем изменения в базе данных
            db_handler.session.commit()
            # Получаем и сохраняем HTML шаблон с контентом группы сообщений для сохранения в файл
            # Формирование набора данных с контентом группы сообщений для возможного сохранения в файловую систему
            message_group_export_data = {
                'message_date': tg_message_group.date.strftime(GlobalConst.message_datetime_format),
                'dialog_title': tg_dialog.title,
                'text': tg_message_group.text,
                'files_report': tg_message_group.files_report,
                'from_id': tg_message_group.from_id,
                'reply_to': tg_message_group.reply_to,
                'files': [{'file_name': Path(tg_file.file_path).name,
                           'alt_text': tg_file.alt_text} for tg_file in tg_message_group.files],
            }
            # Формирование пути к файлу в файловой системе
            file_name = TgFile.get_self_file_name(tg_message_group.date, MessageFileTypes.CONTENT,
                                                  tg_message_group.grouped_id, 0, MessageFileTypes.CONTENT.default_ext)
            file_path = Path(
                ProjectDirs.media_dir) / tg_dialog.get_self_dir() / tg_message_group.get_self_dir() / file_name
            html_content = render_template('export_message.html', **message_group_export_data)
            with open(file_path, 'w', encoding='utf-8') as cf:
                cf.write(html_content)
            # Сбрасываем отметку "сохранить" после сохранения в БД и устанавливаем признак "сохранено"
            tg_message_group.selected = False
            tg_message_group.saved_to_db = True
            # Обновляем список сохраненных диалогов
            db_handler.all_dialogues_list = db_handler.get_dialog_list()
            db_handler.current_state.dialog_list = db_handler.all_dialogues_list.copy()
    return jsonify({FormButtonCfg.db_message_filter.get(
        'dialog_select'): db_handler.get_select_content_string(db_handler.current_state.dialog_list, 'dialog_id',
                                                               'title')})


@tg_saver.route('/sync_local_files_with_db', methods=["POST"])
def sync_local_files_with_db():
    """
    Синхронизация локальных медиа файлов с базой данных
    """
    # Получаем из БД все файлы с указанными расширениями
    file_ext_to_sync = ['.jpg', '.mp4']
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
                                f'Files deleted from local storage: {files_deleted_count}',new_list=True)
    # Удаляем пустые директории
    dir_tree = sorted(Path.walk(Path(ProjectDirs.media_dir)), key=lambda x: len(x[0].as_posix()), reverse=True)
    dir_deleted_count = len([x[0].rmdir() for x in dir_tree if
                             not x[1] and not x[2] and (not x[0].samefile(Path(ProjectDirs.media_dir)))])
    status_messages.mess_update('Synchronizing the list of local files with the database',
                                f'Empty directories deleted from local storage: {dir_deleted_count}')
    # Скачиваем файлы, которые есть в базе данных, но отсутствуют в локальной файловой системе
    downloaded_file_list = []
    for file_path in files_to_download:
        # Получаем информацию о файле из базы данных
        downloaded_file = db_handler.get_file_by_local_path(file_path)
        if downloaded_file:
            downloaded_file_list.append(downloaded_file)
    tg_handler.download_message_file_from_list(downloaded_file_list)
    return jsonify({})


@tg_saver.route('/db_message_apply_filters', methods=['POST'])
def db_message_apply_filters():
    """
    Получение списка сообщений из базы данных с применением фильтров
    """
    # Установка фильтров списка сообщений из базы данных по значениям из формы
    form_cfg = FormButtonCfg.db_message_filter
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
    return jsonify({'db_details': render_template('db_details.html'),
                    FormButtonCfg.db_detail_tags.get(
                        'curr_message_tags'): db_handler.get_select_content_string(
                        db_handler.current_state.message_details.get('tags'), 'id', 'name')})


@tg_saver.route('/db_select_messages', methods=["POST"])
def db_select_messages():
    """
    Обработка отметки сообщений в базе данных в списке сообщений
    """
    # # Получаем id группы сообщений
    # selected_message_group_id = get_dict_value_by_partial_key(request.form, ProjectConst.mess_group_id)
    # # Получаем значение признака сохранения (чекбокса) для группы сообщений
    # is_selected = get_dict_value_by_partial_key(request.form, ProjectConst.select_to_save) is not None
    # # Устанавливаем признак сохранения для выбранной группы сообщений
    # if selected_message_group_id:
    #     tg_handler.get_message_group_by_id(tg_handler.current_state.message_group_list,
    #                                        selected_message_group_id).selected = is_selected
    return jsonify({})


@tg_saver.route('/db_select_details', methods=["POST"])
def db_select_details():
    """
    Обработка отметки для сообщений в базе данных в деталях сообщения
    """
    # # Получаем id группы сообщений
    # selected_message_group_id = get_dict_value_by_partial_key(request.form, ProjectConst.mess_group_id)
    # # Получаем значение признака сохранения (чекбокса) для группы сообщений
    # is_selected = get_dict_value_by_partial_key(request.form, ProjectConst.select_to_save) is not None
    # # Устанавливаем признак сохранения для выбранной группы сообщений
    # if selected_message_group_id:
    #     tg_handler.get_message_group_by_id(tg_handler.current_state.message_group_list,
    #                                        selected_message_group_id).selected = is_selected
    return jsonify({})


@tg_saver.route('/db_tag_add', methods=['POST'])
def db_tag_add():
    """
    Добавление тега к сообщению
    """
    form_cfg = FormButtonCfg.db_detail_tags
    current_tags_select = all_tags_select = None
    tag_name = request.form.get(form_cfg['edit_tag_name'])
    if tag_name:
        current_tags_select, all_tags_select = db_handler.add_tag_to_message_group(tag_name,
                                                                                   db_handler.current_state.selected_message_group_id)
    return jsonify({form_cfg['curr_message_tags']: current_tags_select,
                    form_cfg['all_detail_tags']: all_tags_select})


@tg_saver.route('/db_tag_remove', methods=['POST'])
def db_tag_remove():
    """
    Удаление тега сообщения
    """
    form_cfg = FormButtonCfg.db_detail_tags
    current_tags_select = all_tags_select = None
    tag_name = request.form.get(form_cfg['edit_tag_name'])
    if tag_name:
        current_tags_select, all_tags_select = db_handler.remove_tag_from_message_group(tag_name,
                                                                                        db_handler.current_state.selected_message_group_id)
    return jsonify({form_cfg['curr_message_tags']: current_tags_select,
                    form_cfg['all_detail_tags']: all_tags_select})


@tg_saver.route('/db_tag_update', methods=['POST'])
def db_tag_update():
    """
    Изменение тега сообщения
    """
    form_cfg = FormButtonCfg.db_detail_tags
    current_tags_select = all_tags_select = None
    old_tag_name = request.form.get(form_cfg['old_tag_name'])
    new_tag_name = request.form.get(form_cfg['edit_tag_name'])
    if all([old_tag_name, new_tag_name, new_tag_name != old_tag_name]):
        current_tags_select, all_tags_select = db_handler.update_tag_from_message_group(old_tag_name, new_tag_name,
                                                                                        db_handler.current_state.selected_message_group_id)
    return jsonify({form_cfg['curr_message_tags']: current_tags_select,
                    form_cfg['all_detail_tags']: all_tags_select})


@tg_saver.route('/db_tag_update_everywhere', methods=['POST'])
def db_tag_update_everywhere():
    """
    Изменение тега сообщения и такого же тега всех сообщений
    """
    form_cfg = FormButtonCfg.db_detail_tags
    current_tags_select = all_tags_select = None
    old_tag_name = request.form.get(form_cfg['old_tag_name'])
    new_tag_name = request.form.get(form_cfg['edit_tag_name'])
    if all([old_tag_name, new_tag_name, new_tag_name != old_tag_name]):
        current_tags_select, all_tags_select = db_handler.update_tag_everywhere(old_tag_name, new_tag_name,
                                                                                db_handler.current_state.selected_message_group_id)
    return jsonify({form_cfg['curr_message_tags']: current_tags_select,
                    form_cfg['all_detail_tags']: all_tags_select})


@tg_saver.route('/db_all_tag_sorting', methods=['POST'])
def db_all_tag_sorting():
    """
    Сортировка всех тегов базы данных в поле выбора тегов
    """
    form_cfg = FormButtonCfg.db_detail_tags
    match request.form.get(form_cfg['tag_sorting_field']):
        case '1':
            db_handler.current_state.all_tags_list_sorting = TagsSorting.usage_count_desc
        case '2':
            db_handler.current_state.all_tags_list_sorting = TagsSorting.updated_at_desc
        case _:
            db_handler.current_state.all_tags_list_sorting = TagsSorting.name_asc
    # # Получение списка тегов с сортировкой по текущим установкам
    db_handler.all_tags_list = db_handler.get_all_tag_list()
    return jsonify({form_cfg['all_detail_tags']:
                        db_handler.get_select_content_string(db_handler.all_tags_list, 'id', 'name')})


if __name__ == '__main__':
    tg_saver.run(debug=True, use_reloader=False)

# TODO: проверить на загрузку сообщения с разными типами приложений, почему возвращает ошибку при Unknown, проверить загрузку видео и аудио
# TODO: проверить превращение файловой-статусной строки в ссылку в Message_Group
# TODO: сделать возможность удаления сообщений из базы данных
# TODO: Режимы: автоматические отметки по условию (продумать условия)
# TODO: Режимы: просмотр базы с возможностью удаления
# TODO: Экспорт выделенных постов в Excel файл и HTML, выделенных по условию (продумать условия)
# TODO: Добавить инструкцию по получению своих параметров Телеграм
# TODO: Сделать Unit тесты

# Оставлять архивные подписки в базе
# Режимы: синхронизация чата и базы с условиями (продумать условия)
# Установить отдельно предельные размеры для файлов и медиа разных типов
