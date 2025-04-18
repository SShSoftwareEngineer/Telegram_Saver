from datetime import datetime

from flask import Flask, render_template, request

from telegram_handler import get_dialogs #, get_posts, get_post

tg_saver = Flask(__name__)


@tg_saver.route("/")
def index():
    return render_template("base.html")


@tg_saver.route('/dialogs')
def get_chats():
    # dialogs = telegram.get_dialogs()
    dialogs = ['<a href="#" hx-get="/load_dialog/1" hx-target="#result-div">Dialog 1</a>' for x in range(1, 10)]
    return render_template('dialogs.html', dialogs=dialogs)


@tg_saver.route("/dialogs/<int:dialog_id>")
def get_messages(post_id):
    # messages = get_posts(dialog_id)  # Получаем посты чата
    messages = [f'Message {x}' for x in range(1, 110)]
    return render_template("messages.html", messages=messages)


@tg_saver.route('/message/<int:message_id>')
def get_message_details(message_id):
    # message = telegram.get_message_details(message_id)
    message = {'sender': 'sender',
               'date': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
               'text': 'text text text text text text text text text text text text text text text text text text text'}
    return render_template('details.html', message=message)


@tg_saver.route('/load_dialog/<item_id>')
def load_dialog(item_id):
    # Возвращаем только часть HTML, которая заменит целевой элемент
    return f"<p>Результат: {item_id}</p>"


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
