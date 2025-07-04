from flask import Flask, render_template, request, send_from_directory

from configs.config import ProjectConst, MessageFileTypes
from telegram_handler import TelegramHandler
from database_handler import DatabaseHandler, DbDialog, DbMessageGroup, DbFile, DbDialogType, DbFileType

tg_saver = Flask(__name__)
tg_handler = TelegramHandler()
db_handler = DatabaseHandler()


@tg_saver.route(f'/media_dir/<path:filename>')
def media_dir(filename):
    """
    Регистрация пути для хранения кэшированных изображений.
    Принимает полный путь включая ProjectDirs.media_dir
    """
    return send_from_directory('.', filename)


@tg_saver.context_processor
def inject_field_names():
    """
    Регистрация контекстного процессора с именами полей
    """
    return {
        'date_from_default': tg_handler.message_sort_filter.date_from_default,
        'constants': ProjectConst,
        'file_types': MessageFileTypes,
    }


@tg_saver.route("/")
def index():
    """
    Главная страница приложения
    """
    tg_dialogs = tg_handler.get_dialog_list()
    tg_handler.current_state.dialog_list = tg_dialogs
    if tg_dialogs:
        # Получаем id первого диалога
        tg_handler.current_state.selected_dialog_id = tg_dialogs[0].dialog_id
    return render_template("index.html", tg_dialogs=tg_dialogs)


@tg_saver.route("/tg_dialogs")
def get_tg_dialogs():
    """
    Получение списка диалогов Telegram
    """
    tg_dialogs = tg_handler.get_dialog_list()
    tg_handler.current_state.dialog_list = tg_dialogs
    return render_template("tg_dialogs.html", tg_dialogs=tg_dialogs)


@tg_saver.route("/tg_messages/<string:dialog_id>")
def get_tg_messages(dialog_id):
    """
    Получение списка сообщений при обновлении текущего диалога
    """
    tg_messages = tg_handler.get_message_group_list(int(dialog_id))
    tg_handler.current_state.selected_dialog_id = int(dialog_id)
    tg_handler.current_state.message_group_list = tg_messages
    return render_template("tg_messages.html", tg_messages=tg_messages)


@tg_saver.route('/tg_details/<string:dialog_id>/<string:message_group_id>')
def get_tg_details(dialog_id: str, message_group_id: str):
    """
    Получение детальной информации о сообщении
    """
    tg_details = tg_handler.get_message_detail(int(dialog_id), message_group_id) if message_group_id else None
    tg_handler.current_state.message_details = tg_details
    return render_template("tg_details.html", tg_details=tg_details)


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
    tg_dialogs = tg_handler.get_dialog_list()
    tg_handler.current_state.dialog_list = tg_dialogs
    return render_template("tg_dialogs.html", tg_dialogs=tg_dialogs)


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
    tg_messages = tg_handler.get_message_group_list(tg_handler.current_state.selected_dialog_id)
    tg_handler.current_state.message_group_list = tg_messages
    return render_template("tg_messages.html", tg_messages=tg_messages)


@tg_saver.route('/select_messages_to_save', methods=["POST"])
def select_messages_to_save():
    """
    Обработка отметки сохранения сообщений в базе данных в списке сообщений
    """
    selected_message_group_id = None
    is_selected = False
    for key, value in request.form.items():
        # Получаем id группы сообщений
        if key.find(ProjectConst.mess_group_id) != -1:
            selected_message_group_id = value
        # Получаем флаг сохранения для группы сообщений
        if key.find(ProjectConst.select_to_save) != -1:
            is_selected = value is not None
    # Устанавливаем флаг сохранения для выбранной группы сообщений
    if selected_message_group_id:
        tg_handler.get_message_group_by_id(tg_handler.current_state.message_group_list,
                                           selected_message_group_id).selected = is_selected
    return ''


@tg_saver.route('/select_details_to_save', methods=["POST"])
def select_details_to_save():
    """
    Обработка отметки сохранения сообщений в базе данных в деталях сообщения
    """
    selected_message_group_id = None
    is_selected = False
    for key, value in request.form.items():
        # Получаем id группы сообщений
        if key.find(ProjectConst.mess_group_id) != -1:
            selected_message_group_id = value
        # Получаем флаг сохранения для группы сообщений
        if key.find(ProjectConst.select_to_save) != -1:
            is_selected = value is not None
    # Устанавливаем флаг сохранения для выбранной группы сообщений
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
            filter_fields = dict(dialog_id=tg_dialog.dialog_id)
            update_fields = dict(title=tg_dialog.title,
                                 dialog_type=db_handler.session.query(DbDialogType).filter_by(
                                     type_id=tg_dialog.type.value).first())
            db_dialog = db_handler.upsert_record(DbDialog, filter_fields, update_fields)
            # Сохраняем группу сообщений
            filter_fields = dict(grouped_id=tg_message_group.grouped_id)
            update_fields = dict(date_time=tg_message_group.date,
                                 text=tg_message_group.text,
                                 truncated_text=tg_message_group.truncated_text,
                                 files_report=tg_message_group.files_report,
                                 from_id=tg_message_group.from_id,
                                 reply_to=tg_message_group.reply_to,
                                 dialog=db_dialog)
            db_message_group = db_handler.upsert_record(DbMessageGroup, filter_fields, update_fields)
            # Сохраняем или обновляем данные о файлах сообщений, входящих в группу
            for tg_file in tg_message_group.files:
                filter_fields = dict()
                update_fields = dict(message_id=tg_file.message_id,
                                     file_path=tg_file.file_path,
                                     size=tg_file.size,
                                     message_group=db_message_group,
                                     file_type=db_handler.session.query(DbFileType).filter_by(
                                         type_id=tg_file.file_type.type_id).first())
                db_file = db_handler.upsert_record(DbFile, filter_fields, update_fields)
            # Сохраняем изменения в базе данных
            db_handler.session.commit()
    return ''


if __name__ == '__main__':
    tg_saver.run(debug=True, use_reloader=False)

    # Оставлять архивные подписки в базе
    # Режимы: просмотр чата, отметка на сохранение, автоматические отметки по условию (продумать условия)
    # Режимы: просмотр базы с возможностью удаления
    # Режимы: синхронизация чата и базы с условиями (продумать условия)
    # Экспорт выделенных постов в Excel файл и HTML, выделенных по условию (продумать условия)
    # Проверять есть ли в базе текущее сообщение и если есть, то не добавлять его и грузить из базы
    # Установить отдельно предельные размеры для файлов и медиа разных типов
    # Установить фильтры: непрочитанные сообщения, поиск по тегам.
    # Добавить инструкцию по получению своих параметров Телеграм

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
