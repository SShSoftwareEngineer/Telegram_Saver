from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_file
import asyncio

from telegram_handler import TelegramHandler

tg_saver = Flask(__name__)
tg_handler = TelegramHandler()


@tg_saver.route("/")
def index():
    tg_dialogs = tg_handler.get_dialog_list()
    return render_template("index.html", tg_dialogs=tg_dialogs)


@tg_saver.route("/tg_dialogs")
def get_tg_dialogs():
    # Получаем список сообщений в каждом диалоге по пользовательскому фильтру
    tg_dialogs = tg_handler.get_dialog_list()
    return render_template("tg_dialogs.html", tg_dialogs=tg_dialogs)


@tg_saver.route("/tg_messages/<string:dialog_id>")
def get_tg_messages(dialog_id):
    # Получаем список сообщений в каждом диалоге по пользовательскому фильтру
    tg_handler.current_dialog_id = int(dialog_id)
    tg_handler.message_sort_filter.set_default_filters()
    tg_messages = tg_handler.get_message_list(int(dialog_id))
    return render_template("tg_messages.html", tg_messages=tg_messages)


@tg_saver.route('/tg_details/<string:dialog_id>/<string:message_id>')
def get_tg_details(dialog_id, message_id):
    # Получаем детальную информацию о сообщении
    tg_details = tg_handler.get_message_detail(int(dialog_id), int(message_id))
    return render_template("tg_details.html", tg_details=tg_details)


@tg_saver.route('/tg_dialog_apply_filters', methods=['POST'])
def tg_dialog_apply_filters():
    # Обработка сортировки и фильтра списка диалогов Telegram
    dial_filter = tg_handler.dialog_sort_filter
    form = request.form
    dial_filter.sort_field(form.get('sort_field'))
    dial_filter.reverse(form.get('reverse'))
    dial_filter.type_filter(form.get('type_filter'))
    dial_filter.title_filter(form.get('title_filter'))

    tg_dialogs = tg_handler.get_dialog_list()
    return render_template("tg_dialogs.html", tg_dialogs=tg_dialogs)


@tg_saver.route('/tg_message_apply_filters', methods=['POST'])
def tg_message_apply_filters():
    # Обработка сортировки и фильтра списка сообщений диалога Telegram
    mess_filter = tg_handler.message_sort_filter
    form = request.form
    mess_filter.reverse(form.get('mess_reverse'))
    mess_filter.date_from(form.get('date_from'))
    mess_filter.date_to(form.get('date_to'))
    mess_filter.search(form.get('search'))
    mess_filter.limit(form.get('limit'))

    tg_messages = tg_handler.get_message_list(tg_handler.current_dialog_id)
    return render_template("tg_messages.html", tg_messages=tg_messages)


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
