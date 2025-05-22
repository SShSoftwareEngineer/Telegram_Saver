from flask import Flask, render_template, request, send_from_directory

from telegram_handler import TelegramHandler
from config.config import FieldNames, Constants

tg_saver = Flask(__name__)
tg_handler = TelegramHandler()


@tg_saver.route(f'/cache/<path:filename>')
def cache_media(filename):
    """
    Регистрация пути для хранения кэшированных изображений
    """
    return send_from_directory('chats_media/cache', filename)


@tg_saver.context_processor
def inject_field_names():
    """
    Регистрация контекстного процессора с именами полей
    """
    return {
        'dialog_info': FieldNames.DIALOG_INFO,
        'dialog_settings': FieldNames.DIALOG_SETTINGS,
        'message_group_info': FieldNames.MESSAGE_GROUP_INFO,
        'message_settings': FieldNames.MESSAGE_SETTINGS,
        'details_info': FieldNames.DETAILS_INFO,
        'constants': Constants
    }


@tg_saver.route("/")
def index():
    """
    Главная страница приложения
    """
    tg_dialogs = tg_handler.get_dialog_list()
    if tg_dialogs:
        # Получаем id первого диалога
        tg_handler.current_dialog_id = int(tg_dialogs[0].get(FieldNames.DIALOG_INFO['id']))
    return render_template("index.html", tg_dialogs=tg_dialogs)


@tg_saver.route("/tg_dialogs")
def get_tg_dialogs():
    """
    Получение списка диалогов Telegram
    """
    tg_dialogs = tg_handler.get_dialog_list()
    return render_template("tg_dialogs.html", tg_dialogs=tg_dialogs)


@tg_saver.route("/tg_messages/<string:dialog_id>")
def get_tg_messages(dialog_id):
    """
    Получение списка сообщений при обновлении текущего диалога, применяется фильтр по умолчанию
    """
    tg_handler.current_dialog_id = int(dialog_id)
    tg_handler.message_sort_filter.set_default_filters()
    tg_messages = tg_handler.get_message_list(int(dialog_id))
    return render_template("tg_messages.html", tg_messages=tg_messages)


@tg_saver.route('/tg_details/<string:dialog_id>/<string:message_group_id>')
def get_tg_details(dialog_id, message_group_id):
    """
    Получение детальной информации о сообщении
    """
    tg_details = tg_handler.get_message_detail(int(dialog_id), message_group_id) if message_group_id else None
    return render_template("tg_details.html", tg_details=tg_details)


@tg_saver.route('/tg_dialog_apply_filters', methods=['POST'])
def tg_dialog_apply_filters():
    """
    Получение списка диалогов Telegram с применением фильтров
    """
    # Установка фильтров диалогов по значениям из формы
    dial_filter = tg_handler.dialog_sort_filter
    form = request.form
    field = FieldNames.DIALOG_SETTINGS
    dial_filter.sort_field(form.get(field['sort_field']))
    dial_filter.sort_order(form.get(field['sort_order']))
    dial_filter.dialog_type(form.get(field['dialog_type']))
    dial_filter.title_query(form.get(field['title_query']))
    # Получение списка диалогов с применением фильтров
    tg_dialogs = tg_handler.get_dialog_list()
    return render_template("tg_dialogs.html", tg_dialogs=tg_dialogs)


@tg_saver.route('/tg_message_apply_filters', methods=['POST'])
def tg_message_apply_filters():
    """
    Получение списка сообщений диалога Telegram с применением фильтров
    """
    mess_filter = tg_handler.message_sort_filter
    form = request.form
    field = FieldNames.MESSAGE_SETTINGS
    mess_filter.sort_order(form.get(field['sort_order']))
    mess_filter.date_from(form.get(field['date_from']))
    mess_filter.date_to(form.get(field['date_to']))
    mess_filter.message_query(form.get(field['message_query']))
    # Получение списка сообщений с применением фильтров
    tg_messages = tg_handler.get_message_list(tg_handler.current_dialog_id)
    return render_template("tg_messages.html", tg_messages=tg_messages)


@tg_saver.route('/check_box_test', methods=["POST"])
def check_box_test():
    """
    Тестовая страница для проверки работы чекбоксов
    """
    print(request.form.get('save_to_db'))
    return None


if __name__ == '__main__':
    tg_saver.run(debug=True, use_reloader=False)

    # Оставлять архивные подписки в базе
    # Режимы: просмотр чата, отметка на сохранение, автоматические отметки по условию (продумать условия)
    # Режимы: просмотр базы с возможностью удаления
    # Режимы: синхронизация чата и базы с условиями (продумать условия)
    # Экспорт выделенных постов в Excel файл и HTML, выделенных по условию (продумать условия)
    # Проверять есть ли в базе текущее сообщение и если есть, то не добавлять его и грузить из базы
    # Установить отдельно предельные размеры для файлов и медиа разных типов
    # Установить фильтры: непрочитанные сообщения, диапазон дат, поиск по тегам, поиск по тексту
    # Сделать гиперссылки в сообщениях
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
