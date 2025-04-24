from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_file
import asyncio

from telegram_handler import TelegramHandler

tg_saver = Flask(__name__)
tg_handler = TelegramHandler()


@tg_saver.route("/")
def index():
    return render_template("index.html")


@tg_saver.route("/tg_dialogs")
def get_tg_dialogs():
    # Получаем список сообщений в каждом диалоге по пользовательскому фильтру
    tg_dialogs = tg_handler.get_dialog_list()
    return render_template("tg_dialogs.html", tg_dialogs=tg_dialogs)


@tg_saver.route("/tg_messages/<string:dialog_id>")
def get_tg_messages(dialog_id):
    # Получаем список сообщений в каждом диалоге по пользовательскому фильтру
    tg_messages = tg_handler.get_dialog_messages(int(dialog_id))
    return render_template("tg_messages.html", tg_messages=tg_messages)


@tg_saver.route('/tg_details/<string:dialog_id>/<string:message_id>')
def get_tg_details(dialog_id, message_id):
    # Получаем детальную информацию о сообщении
    tg_details = tg_handler.get_message_detail(int(dialog_id), int(message_id))
    return render_template("tg_details.html", tg_details=tg_details)


@tg_saver.route('/tg_sorting_selection', methods=['POST'])
def tg_sorting_selection():
    # Обработка порядка сортировки списка диалогов
    choice = request.form.get('choice')
    return f"<p>Результат: {choice}</p>"


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
