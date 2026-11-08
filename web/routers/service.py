"""
Service routes: the main page and the status bar.
Служебные маршруты: главная страница и строка статуса.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from telegram_handler import get_tg_handler
from utils import status_messages
from web.deps import state_lock, templates

router = APIRouter()


@router.get('/status_output')
def status_output() -> JSONResponse:
    """
    Updating the status bar. Without the lock: the page polls it while long operations hold the lock.
    Обновление строки статуса. Без замка: страница опрашивает его, пока долгие операции держат замок.
    """
    return JSONResponse(status_messages.messages)


@router.get('/', response_class=HTMLResponse)
def index(request: Request):
    """
    Application home page
    Главная страница приложения
    """
    with state_lock:
        dialog_list = get_tg_handler().current_state.dialog_list
        chats_count = f'({len(dialog_list)})' if dialog_list else ''
        # Rendering the main page template with displaying the number of Telegram chats
        # Рендеринг шаблона главной страницы с отображением количества чатов Telegram
        return templates.TemplateResponse(request, 'index.html', {'chats_count': chats_count})
