"""
Middleware of the web layer.
Middleware веб-слоя.

RequestGuard: rejects requests that are not addressed to the local server or come from a foreign web page
OperationTracker: marks the status bar operation as finished (or failed) when the request that used it is over
"""

import logging
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from config import HOST, PORT
from utils import request_status_touches, status_messages

logger = logging.getLogger(__name__)

# The values of the `Host` header and of the `Origin` header (scheme and port included) the server accepts
# Значения заголовков `Host` и `Origin` (со схемой и портом), которые принимает сервер
ALLOWED_HOSTS = frozenset({f'{HOST}:{PORT}', f'localhost:{PORT}'})
ALLOWED_ORIGINS = frozenset(f'http://{host}' for host in ALLOWED_HOSTS)


class RequestGuard:
    """
    A pure ASGI middleware protecting the local single-user server from web pages open in the user's browser
    (CSRF) and from DNS rebinding. A request is rejected with 403 JSON when:
      - `Host` is not the server address (DNS rebinding: a foreign domain pointing to 127.0.0.1);
      - `Origin` is present and is not the server address (the browser sets it on cross-origin requests and a page
        cannot forge it; `null` is rejected too). A request without `Origin` (curl, tests) passes: a browser always
        sends it on a cross-origin POST;
      - `Sec-Fetch-Site` is `cross-site` (a foreign site, including GET requests such as `<img src>`), except the
        main page `/`: a link from another site legitimately opens it and the page changes nothing. A browser
        without this header (or a program) passes.
    Защищает локальный однопользовательский сервер от веб-страниц, открытых в браузере пользователя (CSRF), и от
    DNS rebinding. Запрос отклоняется с ответом 403 JSON, если:
      - `Host` - не адрес сервера (DNS rebinding: чужой домен, указывающий на 127.0.0.1);
      - `Origin` есть и не совпадает с адресом сервера (браузер ставит его на кросс-доменных запросах, страница не
        может его подделать; `null` тоже отклоняется). Запрос без `Origin` (curl, тесты) проходит: на кросс-доменном
        POST браузер его отправляет всегда;
      - `Sec-Fetch-Site` равен `cross-site` (чужой сайт, в том числе GET вроде `<img src>`), кроме главной страницы
        `/`: ссылка с другого сайта открывает ее законно, а страница ничего не меняет. Браузер без этого заголовка
        (или программа) проходит.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    @staticmethod
    def reject_reason(scope: Scope) -> str | None:
        """
        Returns the reason to reject the request, or None if it is accepted.
        Возвращает причину отклонения запроса или None, если запрос принят.
        """
        headers = Headers(scope=scope)
        host = headers.get('host')
        if host not in ALLOWED_HOSTS:
            return f'foreign Host {host!r}'
        origin = headers.get('origin')
        if origin is not None and origin not in ALLOWED_ORIGINS:
            return f'foreign Origin {origin!r}'
        is_main_page = scope['method'] in ('GET', 'HEAD') and scope['path'] == '/'
        if headers.get('sec-fetch-site') == 'cross-site' and not is_main_page:
            return 'cross-site request'
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        reason = self.reject_reason(scope)
        if reason:
            logger.warning('Request rejected (%s): %s %s', reason, scope['method'], scope['path'])
            await JSONResponse({'error': 'Forbidden'}, status_code=403)(scope, receive, send)
            return
        await self.app(scope, receive, send)


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
