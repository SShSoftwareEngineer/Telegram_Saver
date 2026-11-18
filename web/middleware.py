"""
Middleware of the web layer.
Middleware веб-слоя.

OperationTracker: marks the status bar operation as finished (or failed) when the request that used it is over
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send
from utils import request_status_touches, status_messages


class OperationTracker:
    """
    A pure ASGI middleware for the whole application, so new routes need nothing. A request that called
    `status_messages.mess_update` (the list in `request_status_touches` is not empty) finishes its operation: a check
    mark for a response below 400, a cross for an error response or an exception. Other requests (the page, the status
    poll, static files, routes without a status) leave the status bar alone. Requests run one by one under the shared
    lock, so one operation at a time is expected.
    Чистый ASGI middleware на все приложение, поэтому новым роутам ничего не нужно. Запрос, вызвавший
    `status_messages.mess_update` (список в `request_status_touches` не пуст), завершает свою операцию: галочка при
    ответе ниже 400, крестик при ответе с ошибкой или исключении. Остальные запросы (страница, опрос статуса,
    статика, роуты без статуса) строку статуса не трогают. Запросы идут по одному под общим замком, поэтому ожидается
    одна операция за раз.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        touches: list[bool] = []
        token = request_status_touches.set(touches)
        status_code = 200

        async def send_wrapper(message: Message):
            nonlocal status_code
            if message['type'] == 'http.response.start':
                status_code = message['status']
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            if touches:
                status_messages.finish(error=True)
            raise
        finally:
            request_status_touches.reset(token)
        if touches:
            status_messages.finish(error=status_code >= 400)
