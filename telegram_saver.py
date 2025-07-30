from pathlib import Path
from typing import Optional

from flask import Flask, render_template, request, send_from_directory
from sqlalchemy import or_

from configs.config import ProjectConst, MessageFileTypes, ProjectDirs
from telegram_handler import TelegramHandler
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
        'date_from_default': tg_handler.message_sort_filter.date_from_default,
        'constants': ProjectConst,
        'file_types': MessageFileTypes,
        'tg_dialogs': tg_handler.current_state.dialog_list,
        'tg_messages': tg_handler.current_state.message_group_list,
        'tg_details': tg_handler.current_state.message_details,
        'db_dialog_list': db_handler.all_dialogues_list,
    }


def initialize_data():
    """
    Инициализация данных при запуске
    """
    pass


# Инициализация после создания приложения
with tg_saver.app_context():
    initialize_data()


@tg_saver.route(f'/media_dir/<path:filename>')
def media_dir(filename):
    """
    Регистрация пути для хранения кэшированных изображений.
    Принимает полный путь включая ProjectDirs.media_dir
    """
    return send_from_directory('.', filename)


@tg_saver.route("/")
def index():
    """
    Главная страница приложения
    """
    return render_template("index.html")


@tg_saver.route("/tg_dialogs")
def get_tg_dialogs():
    """
    Получение списка диалогов Telegram
    """
    tg_handler.current_state.dialog_list = tg_handler.get_tg_dialog_list()
    return render_template("tg_dialogs.html")


@tg_saver.route("/tg_messages/<string:dialog_id>")
def get_tg_messages(dialog_id):
    """
    Получение списка сообщений при обновлении текущего диалога
    """
    # Получаем список групп сообщений для выбранного диалога
    tg_message_groups = tg_handler.get_message_group_list(int(dialog_id))
    # Проверяем какие группы сообщений уже сохранены в базе данных
    message_group_ids = [tg_message_group.grouped_id for tg_message_group in tg_message_groups]
    saved_group_ids = set(db_handler.session.query(DbMessageGroup.grouped_id)
                          .filter(DbMessageGroup.grouped_id.in_(message_group_ids)).all())
    saved_group_ids = [x[0] for x in saved_group_ids]
    # Устанавливаем признак сохранения для групп сообщений, которые уже сохранены в базе данных
    for tg_message_group in tg_message_groups:
        tg_message_group.saved_to_db = tg_message_group.grouped_id in saved_group_ids
    # Устанавливаем текущее состояние диалога и списка групп сообщений
    tg_handler.current_state.selected_dialog_id = int(dialog_id)
    tg_handler.current_state.message_group_list = tg_message_groups
    return render_template("tg_messages.html")


@tg_saver.route('/tg_details/<string:dialog_id>/<string:message_group_id>')
def get_tg_details(dialog_id: str, message_group_id: str):
    """
    Получение детальной информации о сообщении
    """
    tg_handler.current_state.message_details = tg_handler.get_message_detail(int(dialog_id),
                                                                             message_group_id) if message_group_id else None
    return render_template("tg_details.html")


@tg_saver.route('/tg_dialog_apply_filters', methods=['POST'])
def tg_dialog_apply_filters():
    """
    Получение списка диалогов Telegram с применением фильтров
    """
    # Установка фильтров диалогов по значениям из формы
    dial_filter = tg_handler.dialog_sort_filter
    form = request.form
    dial_filter.sort_field(form.get('sorting_field'))
    dial_filter.sort_order(form.get('sort_order'))
    dial_filter.dialog_type(form.get('dialog_type'))
    dial_filter.title_query(form.get('title_query'))
    # Получение списка диалогов с применением фильтров
    tg_handler.current_state.dialog_list = tg_handler.get_tg_dialog_list()
    return render_template("tg_dialogs.html")


@tg_saver.route('/tg_message_apply_filters', methods=['POST'])
def tg_message_apply_filters():
    """
    Получение списка сообщений диалога Telegram с применением фильтров
    """
    mess_filter = tg_handler.message_sort_filter
    form = request.form
    mess_filter.sort_order = form.get('sort_order')
    mess_filter.date_from = form.get('date_from')
    mess_filter.date_to = form.get('date_to')
    mess_filter.message_query = form.get('message_query')
    # Получение списка сообщений с применением фильтров
    tg_handler.current_state.message_group_list = tg_handler.get_message_group_list(
        tg_handler.current_state.selected_dialog_id)
    return render_template("tg_messages.html")


def get_dict_value_by_partial_key(my_dict: dict, key_part: str) -> Optional[str]:
    """
    Получает значение из словаря по части ключа
    """
    for key, value in my_dict.items():
        if key_part in key:
            return value
    return None


@tg_saver.route('/select_messages_to_save', methods=["POST"])
def select_messages_to_save():
    """
    Обработка отметки сохранения сообщений в базе данных в списке сообщений
    """
    # Получаем id группы сообщений
    selected_message_group_id = get_dict_value_by_partial_key(request.form, ProjectConst.mess_group_id)
    # Получаем значение признака сохранения (чекбокса) для группы сообщений
    is_selected = get_dict_value_by_partial_key(request.form, ProjectConst.select_to_save) is not None
    # Устанавливаем признак сохранения для выбранной группы сообщений
    if selected_message_group_id:
        tg_handler.get_message_group_by_id(tg_handler.current_state.message_group_list,
                                           selected_message_group_id).selected = is_selected
    return ''


@tg_saver.route('/select_details_to_save', methods=["POST"])
def select_details_to_save():
    """
    Обработка отметки сохранения сообщений в базе данных в деталях сообщения
    """
    # Получаем id группы сообщений
    selected_message_group_id = get_dict_value_by_partial_key(request.form, ProjectConst.mess_group_id)
    # Получаем значение признака сохранения (чекбокса) для группы сообщений
    is_selected = get_dict_value_by_partial_key(request.form, ProjectConst.select_to_save) is not None
    # Устанавливаем признак сохранения для выбранной группы сообщений
    if selected_message_group_id:
        tg_handler.get_message_group_by_id(tg_handler.current_state.message_group_list,
                                           selected_message_group_id).selected = is_selected
    return ''


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
            # Устанавливаем relationship для диалога
            if db_dialog.dialog_type is None:
                db_dialog.dialog_type = db_handler.session.query(DbDialogType).filter_by(
                    dialog_type_id=tg_dialog.type.value).first()
            # Сохраняем группу сообщений
            db_message_group = db_handler.upsert_record(DbMessageGroup, dict(grouped_id=tg_message_group.grouped_id),
                                                        dict(date_time=tg_message_group.date,
                                                             text=tg_message_group.text,
                                                             truncated_text=tg_message_group.truncated_text,
                                                             files_report=tg_message_group.files_report,
                                                             from_id=tg_message_group.from_id,
                                                             reply_to=tg_message_group.reply_to,
                                                             dialog_id=tg_dialog.dialog_id))
            # Устанавливаем relationship для группы сообщений
            if db_message_group.dialog is None:
                db_message_group.dialog = db_dialog
            # Сохраняем или обновляем данные о файлах сообщений, входящих в группу
            for tg_file in tg_message_group.files:
                db_file = db_handler.upsert_record(DbFile, dict(file_path=tg_file.file_path),
                                                   dict(message_id=tg_file.message_id,
                                                        size=tg_file.size,
                                                        grouped_id=tg_message_group.grouped_id,
                                                        file_type_id=tg_file.file_type.type_id))
                # Устанавливаем relationships для файла
                if db_file.message_group is None:
                    db_file.message_group = db_message_group
                if db_file.file_type is None:
                    db_file.file_type = db_handler.session.query(DbFileType).filter_by(
                        file_type_id=tg_file.file_type.type_id).first()
                # Скачиваем файл, если его нет в заданной директории файловой системы и его размер меньше предельного
                print(f'Downloading file {tg_file.file_path}...')
                downloading_result = tg_handler.download_message_file(tg_file)
                if downloading_result:
                    print(f'File {tg_file.file_path} downloaded successfully')
                else:
                    print(f'Failed to download file {tg_file.file_path}')
            # Сохраняем изменения в базе данных
            db_handler.session.commit()
            # Получаем и сохраняем HTML шаблон с контентом группы сообщений для сохранения в файл
            # Формирование набора данных с контентом группы сообщений для возможного сохранения в файловую систему
            message_group_export_data = {
                'message_date': tg_message_group.date.strftime(ProjectConst.message_datetime_format),
                'dialog_title': tg_dialog.title,
                'text': tg_message_group.text,
                'files_report': tg_message_group.files_report,
                'from_id': tg_message_group.from_id,
                'reply_to': tg_message_group.reply_to,
                'files': [{'file_name': Path(tg_file.file_path).name,
                           'alt_text': tg_file.alt_text} for tg_file in tg_message_group.files],
            }
            html_content = render_template('export_message.html', **message_group_export_data)
            message_group_time = tg_message_group.date.astimezone().strftime('%H-%M-%S')
            file_name = (f'{message_group_time}_{MessageFileTypes.CONTENT.sign}_'
                         f'{tg_message_group.grouped_id}{MessageFileTypes.CONTENT.default_ext}')
            file_path = Path(
                ProjectDirs.media_dir) / tg_dialog.get_self_dir() / tg_message_group.get_self_dir() / file_name
            with open(file_path, 'w', encoding='utf-8') as cf:
                cf.write(html_content)
            # Сбрасываем отметку "сохранить" после сохранения в БД и устанавливаем признак "сохранено"
            tg_message_group.selected = False
            tg_message_group.saved_to_db = True
    return ''


@tg_saver.route('/sync_local_files_with_db', methods=["POST"])
def sync_local_files_with_db():
    """
    Синхронизация локальных медиа файлов с базой данных
    """
    ext_to_sync = ['.jpg', '.mp4']
    # Получаем из БД все файлы с указанными расширениями
    database_files = db_handler.session.query(DbFile.file_path).filter(
        or_(*[DbFile.file_path.endswith(ext) for ext in ext_to_sync])).all()
    database_files = set([x[0] for x in database_files])
    # Находим все локальные файлы с указанными расширениями рекурсивно
    local_files = []
    for ext in ext_to_sync:
        local_files.extend(Path(ProjectDirs.media_dir).rglob(f'**/*{ext}'))
    local_files = set([x.as_posix() for x in local_files])
    # Сравниваем списки и находим файлы, какие надо удалить и какие нужно докачать
    files_to_delete = local_files - database_files
    files_to_download = database_files - local_files
    # Удаляем файлы, которые есть в локальной файловой системе, но отсутствуют в базе данных
    deleted_count = len([Path(x).unlink() for x in files_to_delete if Path(x).exists()])
    print(f'Deleted {deleted_count} files from local storage')
    # Скачиваем файлы, которые есть в базе данных, но отсутствуют в локальной файловой системе
    downloaded_file_list = []
    for file_path in files_to_download:
        # Получаем информацию о файле из базы данных
        db_file = db_handler.session.query(DbFile).filter_by(file_path=file_path).first()
        if db_file:
            downloaded_file=dict(dialog_id= db_file.message_group.dialog_id,
                                 message_id=db_file.message_id,
                                 file_path=db_file.file_path,
                                 size= db_file.size,
                                 file_type_id=db_file.file_type_id,)
            downloaded_file_list.append(downloaded_file)
    tg_handler.download_message_file_from_list(downloaded_file_list)
    return ''


if __name__ == '__main__':
    tg_saver.run(debug=True, use_reloader=False)

# TODO: продумать, возможно сохранять текст сообщения в HTML файл с локальными ссылками на файлы
# TODO: проверить на загрузку сообщения с разными типами приложений, почему возвращает ошибку при Unknown, проверить загрузку видео и аудио
# TODO: проверить превращение файловой-статусной строки в ссылку в Message_Group
# TODO: сделать поиск по тегам, поиск без тегов, поиск по дате, по диалогу, по тексту сообщения
# TODO: Режимы: автоматические отметки по условию (продумать условия)
# TODO: Режимы: просмотр базы с возможностью удаления
# TODO: Экспорт выделенных постов в Excel файл и HTML, выделенных по условию (продумать условия)
# TODO: Добавить инструкцию по получению своих параметров Телеграм

# Оставлять архивные подписки в базе
# Режимы: синхронизация чата и базы с условиями (продумать условия)
# Установить отдельно предельные размеры для файлов и медиа разных типов

# with tg_saver.test_request_context("/tg_dialogs"):
#     result = get_tg_dialogs()

# with tg_saver.test_request_context('/set_table_headers'):
#     # Теперь доступен request как при настоящем запросе
#     result = set_table_headers()
#     # return f"Handler1 called Handler2 via HTTP context: {result}"

# @tg_saver.route('/update_headers', methods=['POST'])
# def set_table_headers():
#     """
#     Установка заголовков таблицы
#     """
#     response = make_response(render_template('table_headers.html'))
#
#     # Указываем, какое событие нужно вызвать
#     # Это запустит обновление заголовка без необходимости JS
#     response.headers["HX-Trigger"] = "update-header-now"
#     return response
