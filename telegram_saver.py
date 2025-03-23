from telethon import TelegramClient
from flask import Flask, request


def get_chat_list() -> list:
    pass


def get_chat_history(chat_id: int):
    pass


def main():
    pass


app = Flask(__name__)


@app.route('/', methods=['GET', 'POST'])
def index() -> str:
    return jsonify({})


if __name__ == "__main__":
    app.run(debug=True)
    # main()
