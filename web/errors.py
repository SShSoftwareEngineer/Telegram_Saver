"""
Exception handlers of the web layer: every error is returned as JSON (the page scripts expect JSON).
Обработчики исключений веб-слоя: любая ошибка возвращается в виде JSON (скрипты страницы ожидают JSON).

register_error_handlers: registers the handlers in the application
"""

import html
import logging
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from database_handler import get_db_handler
from utils import status_messages
from web.deps import state_lock

logger = logging.getLogger(__name__)


async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    HTTP errors (404, 405 and so on) as JSON: {"error": "<text>"}.
    HTTP-ошибки (404, 405 и т.д.) в виде JSON: {"error": "<текст>"}.
    """
    return JSONResponse({'error': str(exc.detail)}, status_code=exc.status_code, headers=exc.headers)


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Invalid request parameters (422) as JSON, the details of every field are in `detail`.
    Неверные параметры запроса (422) в виде JSON, подробности по каждому полю - в `detail`.
    """
    return JSONResponse({'error': 'Invalid request', 'detail': jsonable_encoder(exc.errors())}, status_code=422)


def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Any unhandled exception: logs it, rolls the shared database session back, shows the error in the status bar
    and returns JSON with the status 500. It is a regular function on purpose: Starlette runs it in a thread, so
    waiting for the state lock does not block the event loop.
    Любое необработанное исключение: логирует его, откатывает общую сессию БД, показывает ошибку в строке статуса
    и возвращает JSON со статусом 500. Это обычная функция намеренно: Starlette запускает ее в потоке, поэтому
    ожидание замка состояния не блокирует event loop.
    """
    logger.error('Unhandled error in %s %s', request.method, request.url.path, exc_info=exc)
    message = f'{type(exc).__name__}: {exc}'
    try:
        # The lock is free here: the route has already left its `with state_lock`
        # Замок здесь свободен: роут уже вышел из своего `with state_lock`
        with state_lock:
            # Without a rollback one failed query leaves the session in PendingRollbackError until a restart
            # Без отката один неудачный запрос оставляет сессию в PendingRollbackError до перезапуска
            get_db_handler().session.rollback()
    except Exception:  # pylint: disable=broad-exception-caught
        logger.exception('Session rollback failed')
    # The status bar text goes to innerHTML on the page, so it is escaped
    # Текст строки статуса вставляется на странице через innerHTML, поэтому он экранируется
    status_messages.mess_update(html.escape(f'Error in {request.url.path}'), html.escape(message))
    return JSONResponse({'error': message}, status_code=500)


def register_error_handlers(app: FastAPI) -> None:
    """
    Registers the JSON exception handlers in the application.
    Регистрирует JSON-обработчики исключений в приложении.
    """
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)
