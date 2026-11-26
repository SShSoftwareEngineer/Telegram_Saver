"""
Contract between the routes and the page script (`updateElementsFromResponse` in `static/js/my_scripts.js`).
Контракт между роутами и скриптом страницы (`updateElementsFromResponse` в `static/js/my_scripts.js`).

A successful response (status 2xx) is a JSON object with two optional sections, both map an element `id` to a value:
    html (dict[str, str]): the new inner HTML of the element (lists, counters, the options of a `<select>`)
    checked (dict[str, bool]): the new `checked` state of a checkbox
An empty object means "nothing to change". The page skips the ids it does not find (a warning in the console).
A failed response (any other status) is `{"error": "<text>"}`: the page shows the text in the status bar.
Успешный ответ (статус 2xx) - JSON-объект с двумя необязательными секциями, обе сопоставляют `id` элемента значению:
    html (dict[str, str]): новое содержимое (innerHTML) элемента (списки, счетчики, пункты `<select>`)
    checked (dict[str, bool]): новое состояние `checked` чек-бокса
Пустой объект означает «менять нечего». Страница пропускает `id`, которых не нашла (предупреждение в консоли).
Ответ с ошибкой (любой другой статус) - `{"error": "<текст>"}`: страница показывает текст в строке статуса.

ui_content: builds the body of a successful response
ui_update: builds a successful response of the contract
"""

from collections.abc import Mapping
from typing import Any
from fastapi.responses import JSONResponse


def ui_content(html: Mapping[str, str | None] | None = None,
               checked: Mapping[str, bool] | None = None) -> dict[str, Any]:
    """
    The body of a successful response: the non-empty sections only; the entries of `html` with the value `None` are
    dropped (the route has nothing to put there, e.g. no tag operation was done).
    Тело успешного ответа: только непустые секции; записи `html` со значением `None` отбрасываются (роуту нечего туда
    положить, например, операция с тегами не выполнялась).
    Attributes:
        html (Mapping[str, str | None] | None): element id -> inner HTML / id элемента -> его HTML
        checked (Mapping[str, bool] | None): checkbox id -> `checked` state / id чек-бокса -> состояние `checked`
    """
    content: dict[str, Any] = {}
    html_section = {key: value for key, value in (html or {}).items() if value is not None}
    if html_section:
        content['html'] = html_section
    if checked:
        content['checked'] = dict(checked)
    return content


def ui_update(html: Mapping[str, str | None] | None = None, checked: Mapping[str, bool] | None = None, *,
              headers: Mapping[str, str] | None = None) -> JSONResponse:
    """
    A successful response of the contract (see the module description).
    Успешный ответ контракта (см. описание модуля).
    Attributes:
        html (Mapping[str, str | None] | None): element id -> inner HTML / id элемента -> его HTML
        checked (Mapping[str, bool] | None): checkbox id -> `checked` state / id чек-бокса -> состояние `checked`
        headers (Mapping[str, str] | None): extra response headers / дополнительные заголовки ответа
    """
    return JSONResponse(ui_content(html, checked), headers=dict(headers) if headers else None)
