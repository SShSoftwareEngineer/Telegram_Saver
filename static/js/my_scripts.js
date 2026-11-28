// Function that implements switching between tabs / Функция, реализующая переключение между вкладками
function openTab(evt, tabName) {
    // Hide all tab contents / Скрываем все содержимое вкладок
    const tabContents = document.querySelectorAll('.tab-content');
    tabContents.forEach(tab => {
        tab.style.display = "none";
    });
    // Remove the “active” class from all tab buttons / Убираем класс "active" со всех кнопок вкладок
    const tabButtons = document.querySelectorAll('.tab-button');
    tabButtons.forEach(button => {
        button.classList.remove("active");
    });
    // Display the current tab and add the “active” class to the button
    // Показываем текущую вкладку и добавляем класс "active" к кнопке
    /** @type {HTMLElement} */
    const tabElement = document.getElementById(tabName);
    tabElement.style.display = "block";
    evt.currentTarget.classList.add("active");
}


// Functions for working with form controls by ID / Функции для работы с элементами управления формы по ID

// Getting value of the selected radio button by container ID / Получение значения выбранной радиокнопки по ID контейнера
function getRadioValue(identifier) {
    const container = document.getElementById(identifier);
    if (!container) return null;
    const checked = container.querySelector('input[type="radio"]:checked');
    return checked ? checked.value : null;
}


// Getting the value of a text field or textarea by ID / Получение значения текстового поля или textarea по ID
function getInputValue(id) {
    /** @type {HTMLInputElement} */
    const input = document.getElementById(id);
    return input ? input.value.trim() : '';
}

// Getting the values of selected rows in select by ID / Получение значения выбранных строк в select по ID
function getSelectValue(id) {
    /** @type {HTMLSelectElement} */
    const select = document.getElementById(id);
    if (!select) return '';
    // If select with multiple choices / Если select с множественным выбором
    if (select.hasAttribute('multiple')) {
        // Return the array of selected values / Возвращаем массив выбранных значений
        const selectedValues = Array.from(select.selectedOptions).map(option => option.value);
        return selectedValues.length > 0 ? selectedValues : '';
    } else {
        // Regular select - return a single value / Обычный select - возвращаем одно значение
        return select.value;
    }
}

// Retrieving the texts of all rows selected in select by ID / Получение по ID текстов всех выбранных строк select
function getSelectTexts(id) {
    /** @type {HTMLSelectElement} */
    const select = document.getElementById(id);
    return select ? Array.from(select.selectedOptions).map(option => option.text) : [];
}

// Fills the tag name field and its hidden old name from a tag list when exactly one tag is selected in it; with
// several tags (or none) both are cleared, so "Update tag" never renames a tag the user did not point at
// Заполняет поле имени тега и его скрытое старое имя из списка тегов, когда в нем выбран ровно один тег; при нескольких
// тегах (или ни одном) оба очищаются, чтобы «Update tag» не переименовал тег, на который пользователь не указывал
// The special "(No tags)" item (class `no-tags-option`) is not a tag: it only goes to the filter, so it never fills the
// fields / Особый пункт «(No tags)» (класс `no-tags-option`) не тег: он только переносится в фильтр, поля не заполняет
function selectTagForEdit(select, editFieldId, oldFieldId) {
    const options = Array.from(select.selectedOptions);
    const texts = options.map(option => option.text);
    const name = texts.length === 1 && !options[0].classList.contains('no-tags-option') ? texts[0] : '';
    setInputValue(editFieldId, name);
    setInputValue(oldFieldId, name);
    // The selection changed: refresh the buttons that need a selected row / Выбор изменился: обновляем кнопки,
    // которым нужна выбранная строка
    updateCheckedDependentButtons();
}

// Getting the value of a multiple-choice checkbox group by container ID
// Получение значения множественного выбора checkbox группы по ID контейнера
function getCheckboxValues(id) {
    const container = document.getElementById(id);
    if (!container) return [];
    const checkboxes = container.querySelectorAll('input[type="checkbox"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

// Universal add function with form data validation in FormData
// Универсальная функция добавления с проверкой данных формы в FormData
function appendIfExists(formData, name, value) {
    if (value === null || value === undefined || value === '') {
        return;
    }
    // If the value is an array (from multiple select) / Если значение - массив (из multiple select)
    if (Array.isArray(value)) {
        value.forEach(item => formData.append(name, item));
    } else {
        formData.append(name, value);
    }
}

// Universal function for collecting form data and sending it to the server
// Универсальная функция сбора данных формы и отправки их на сервер
function submitFormData(config, url, button = null) {
    const formData = new FormData();
    // Radio button processing / Обработка радиокнопок
    (config.radio || []).forEach(field =>
        appendIfExists(formData, field.name, getRadioValue(field.id))
    );
    // Input processing / Обработка input
    (config.input || []).forEach(field =>
        appendIfExists(formData, field.name, getInputValue(field.id))
    );
    // Select processing / Обработка select
    (config.select || []).forEach(field =>
        appendIfExists(formData, field.name, getSelectValue(field.id))
    );
    // Processing a group of checkboxes linked by a single name processes an array of checkbox values.
    // Обработка checkbox группы, объединенных одним name, обрабатывает массив значений checkbox
    (config.checkbox || []).forEach(field => {
        const values = getCheckboxValues(field.id);
        values.forEach(value => formData.append(field.name, value));
    });
    // Processing the ID checkbox list (not groups), processes the ID checkbox array
    // Обработка списка ID checkbox (не группы), обрабатывает массив ID чекбоксов
    const checkboxList = config.checkbox_list || [];
    checkboxList.forEach(field => {
        const selected = document.querySelectorAll(`${field.selector}:checked`);
        const selectedIds = Array.from(selected).map(cb => cb.id);
        selectedIds.forEach(id => {
            formData.append(field.name, id);
        });
    });

    // Sending a request and returning a Promise with the response data (null if the request failed: the error is
    // already shown in the status bar) / Отправка запроса и возврат Promise с данными ответа (null, если запрос не
    // удался: ошибка уже показана в строке статуса)
    return requestJSON(url, {method: 'POST', body: formData}, button);
}

// The contract of the server responses (see `web/ui.py`): a successful response is an object with the optional
// sections `html` ({element id: new inner HTML}) and `checked` ({checkbox id: state}); a failed one (status is not 2xx)
// is `{"error": "<text>"}`
// Контракт ответов сервера (см. `web/ui.py`): успешный ответ - объект с необязательными секциями `html`
// ({id элемента: новый HTML}) и `checked` ({id чек-бокса: состояние}); неудачный (статус не 2xx) -
// `{"error": "<текст>"}`

// The button that is being clicked right now: the inline `onclick` handlers run during the click, so the event is still
// current; null when the call did not come from a button
// Кнопка, которую нажимают прямо сейчас: inline-обработчики `onclick` выполняются во время клика, поэтому событие еще
// текущее; null, если вызов пришел не от кнопки
function clickedButton() {
    const target = window.event ? window.event.currentTarget : null;
    return target instanceof HTMLButtonElement ? target : null;
}

// Marks the button as busy while its request runs: it is disabled (no double click) and shows a spinner
// Помечает кнопку занятой на время ее запроса: она отключена (нет двойного нажатия) и показывает крутилку
function setButtonBusy(button, busy) {
    button.classList.toggle('is-busy', busy);
    button.disabled = busy;
    if (!busy) {
        // The button may depend on the checked items: restore its state from them, not from the state before the request
        // Кнопка может зависеть от отмеченных: восстанавливаем ее состояние по ним, а не по состоянию до запроса
        updateCheckedDependentButtons();
    }
}

// Shows a failed request in the status bar (the same place where the server writes the errors of the operations):
// a cross, the text and a line in the report. The text goes in as text, not as HTML.
// Показывает неудачный запрос в строке статуса (там же, где сервер пишет ошибки операций): крестик, текст и строка
// отчета. Текст вставляется как текст, а не как HTML.
function showRequestError(error) {
    console.error('Request failed:', error);
    const message = error instanceof Error ? error.message : String(error);
    const operation = document.getElementById('sb_operation');
    if (operation) {
        const label = document.createElement('strong');
        label.textContent = 'Operation: ';
        const mark = document.createElement('span');
        mark.className = 'sb-mark';
        mark.title = 'Failed';
        mark.textContent = '❌';
        const text = document.createElement('span');
        text.className = 'sb-operation-text';
        text.title = message;
        text.textContent = message;
        operation.replaceChildren(label, mark, ' ', text);
    }
    const report = document.getElementById('sb_report');
    if (report) {
        const option = document.createElement('option');
        option.textContent = `${new Date().toLocaleTimeString('en-GB')} - ${message}`;
        report.appendChild(option);
        report.selectedIndex = report.options.length - 1;
    }
}

// Sends a request and returns the parsed JSON of the response, or null if the request failed (a network error or a
// non-2xx status: the error text is shown in the status bar). With a `button`, the button is busy until the end.
// Отправляет запрос и возвращает разобранный JSON ответа, либо null, если запрос не удался (ошибка сети или статус
// не 2xx: текст ошибки показан в строке статуса). С `button` кнопка занята до конца запроса.
async function requestJSON(url, options = {}, button = null) {
    if (button) {
        setButtonBusy(button, true);
    }
    try {
        const response = await fetch(url, options);
        let data = {};
        try {
            data = await response.json();
        } catch (parseError) {
            // The body is not JSON (e.g. a proxy error page): the status line is the only thing to show
            // Тело не JSON (например, страница ошибки прокси): показать можно только строку статуса
            if (response.ok) {
                throw new Error('The server answer is not JSON');
            }
        }
        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status} ${response.statusText}`);
        }
        return data;
    } catch (error) {
        showRequestError(error);
        return null;
    } finally {
        if (button) {
            setButtonBusy(button, false);
        }
    }
}

// Universal function for updating elements by the sections of the response (the contract is described above)
// Универсальная функция обновления элементов по секциям ответа (контракт описан выше)
// `resetScroll`: the response loads a new list or new details, so the scroll areas it fills start from the top (after a
// save or a delete the list is the same, so its scroll position is kept)
// `resetScroll`: ответ загружает новый список или новые детали, поэтому заполняемые им области прокрутки начинаются с
// начала (после сохранения или удаления список тот же, поэтому его положение прокрутки сохраняется)
function updateElementsFromResponse(data, resetScroll = false) {
    Object.keys(data).forEach(section => {
        if (section !== 'html' && section !== 'checked') {
            console.warn(`Unknown section '${section}' in the server response`);
        }
    });
    // `html`: the new inner HTML of the elements / `html`: новое содержимое (innerHTML) элементов
    Object.entries(data.html || {}).forEach(([id, markup]) => {
        /** @type {HTMLElement} */
        const element = document.getElementById(id);
        if (!element) {
            console.warn(`Element with ID '${id}' not found on the page`);
            return;
        }
        element.innerHTML = markup;
        if (resetScroll && element.classList.contains('scroll')) {
            element.scrollTop = 0;
        }
        // The chat list of the database tab was redrawn: its selection is gone / Список чатов БД перерисован
        if (id === 'db_dialog_select') syncDbSourceFilter();
    });
    // `checked`: the state of the checkboxes / `checked`: состояние чек-боксов
    Object.entries(data.checked || {}).forEach(([id, state]) => {
        /** @type {HTMLInputElement} */
        const element = document.getElementById(id);
        if (!element) {
            console.warn(`Checkbox with ID '${id}' not found on the page`);
            return;
        }
        // Setting `checked` from code does not fire `change`; fire it for a checkbox that really changed, so its
        // handler (the counter of the checked items) runs, as if the user had clicked it
        // Смена `checked` из кода не вызывает `change`; вызываем его для чек-бокса, который реально изменился,
        // чтобы сработал его обработчик (счетчик отмеченных), как при клике пользователя
        const changed = element.checked !== state;
        element.checked = state;
        if (changed) {
            element.dispatchEvent(new Event('change', {bubbles: true}));
        }
    });
    // A re-rendered list has new (unchecked) checkboxes that fire no `change`: refresh the buttons that need a checked item
    // Перерисованный список содержит новые (неотмеченные) чек-боксы без события `change`: обновляем зависящие от них кнопки
    updateCheckedDependentButtons();
}

// Enables each button marked with `data-needs-checked="<checkbox selector>"` only while at least one such checkbox is
// checked, and disables it otherwise. The same for `data-needs-selected="<select ID>"`: the button works only while
// at least one row of that list is selected
// Включает каждую кнопку с `data-needs-checked="<селектор чек-боксов>"`, только пока отмечен хотя бы один такой
// чек-бокс, иначе отключает ее. То же для `data-needs-selected="<ID списка select>"`: кнопка работает, только пока
// в этом списке выбрана хотя бы одна строка
// A button that is busy with its request (`is-busy`) is skipped: it stays disabled until the request ends
// Кнопка, занятая своим запросом (`is-busy`), пропускается: она остается отключенной до конца запроса
function updateCheckedDependentButtons() {
    document.querySelectorAll('[data-needs-checked]:not(.is-busy)').forEach(button => {
        button.disabled = document.querySelector(`${button.dataset.needsChecked}:checked`) === null;
    });
    document.querySelectorAll('[data-needs-selected]:not(.is-busy)').forEach(button => {
        const select = document.getElementById(button.dataset.needsSelected);
        button.disabled = !select || select.selectedOptions.length === 0;
    });
}

// A page load (also a reload with the checkbox states restored by the browser) / Загрузка страницы (в том числе
// повторная с состоянием чек-боксов, восстановленным браузером)
document.addEventListener('DOMContentLoaded', updateCheckedDependentButtons);
// The browser may restore the chosen chats after the load (reload, back): show the source filter accordingly
// Браузер может восстановить выбранные чаты уже после загрузки (перезагрузка, назад): показать фильтр источников
window.addEventListener('load', () => syncDbSourceFilter());
window.addEventListener('pageshow', () => syncDbSourceFilter());

// Function that implements button press, with configuration of form elements and URL handler
// Функция, реализующая нажатие кнопки, с конфигурацией элементов формы и URL обработчика
// `resetScroll` is true for the buttons that load a new list (the filters), see `updateElementsFromResponse`
// `resetScroll` равен true у кнопок, загружающих новый список (фильтры), см. `updateElementsFromResponse`
// The button that was pressed is busy until the answer (a spinner, no second press), a failure goes to the status bar
// Нажатая кнопка занята до ответа (крутилка, второе нажатие невозможно), ошибка выводится в строку статуса
function pressFormButton(config, url, resetScroll = false) {
    submitFormData(config, url, clickedButton()).then(data => {
        if (data) {
            updateElementsFromResponse(data, resetScroll);
        }
    });
}

// Function that generates a GET request to download data from the server at a specified URL and to update elements
// Функция, формирующая GET-запрос для загрузки данных с сервера с заданного URL и для обновления элементов
function loadURL(url) {
    requestJSON(url, {method: 'GET', headers: {'X-Requested-With': 'XMLHttpRequest'}}).then(data => {
        if (data) {
            // A new chat or new message details: the filled areas start from the top
            // Новый диалог или детали другого сообщения: заполняемые области начинаются с начала
            updateElementsFromResponse(data, true);
        }
    });
}

// Function that calls the handler and updates elements according to the handler's response; the button that was
// pressed is busy until the answer
// Функция, вызывающая обработчик и обновляющая элементы в соответствии с ответом обработчика; нажатая кнопка занята
// до ответа
function callHandler(url) {
    requestJSON(url, {method: 'POST'}, clickedButton()).then(data => {
        if (data) {
            updateElementsFromResponse(data);
        }
    });
}


// The filter by the source chat of the database tab works only for "Saved Messages" (only they have a source): its row
// is shown while the dialog filter is that one chat alone (the CSS reacts to the class `favorites-only`); when it goes
// away its choice is reset, so a hidden choice cannot filter the other chats
// Фильтр по чату-источнику вкладки БД работает только для «Избранного» (только у него есть источник): его строка
// показывается, пока фильтр диалогов - один этот чат (CSS реагирует на класс `favorites-only`); когда она пропадает,
// ее выбор сбрасывается, чтобы скрытый выбор не фильтровал остальные чаты
// Without the argument the ID comes from `data-favorites-id` of the dialog select: that way it also works after the
// browser restores the selection on a reload (no `change` event) and after the server redraws the select
// Без аргумента ID берется из `data-favorites-id` списка диалогов: так работает и после восстановления выбора браузером
// при перезагрузке (события `change` нет), и после перерисовки списка сервером
function syncDbSourceFilter(favoritesId) {
    const dialogSelect = document.getElementById('db_dialog_select');
    const container = document.querySelector('.db-container-tab_2');
    if (!dialogSelect || !container) return;
    if (favoritesId === undefined) favoritesId = dialogSelect.dataset.favoritesId;
    const selected = Array.from(dialogSelect.selectedOptions).map(option => option.value);
    const favoritesOnly = selected.length === 1 && selected[0] === String(favoritesId);
    container.classList.toggle('favorites-only', favoritesOnly);
    const sourceSelect = document.getElementById('db_source_select');
    if (!favoritesOnly && sourceSelect) {
        sourceSelect.value = '';
    }
}


// Setting element values by ID
// Установка значения элементов по ID

// Setting the radio button value by container ID / Установка значения радиокнопки по ID контейнера
function setRadioValue(containerId, value) {
    const container = document.getElementById(containerId);
    if (!container) return false;
    const radio = container.querySelector(`input[type="radio"][value="${value}"]`);
    if (radio) {
        radio.checked = true;
        return true;
    }
    return false;
}

// Setting the value of the input field by ID / Установка значения поля ввода по ID
function setInputValue(id, value) {
    const input = document.getElementById(id);
    if (input) {
        input.value = value;
        return true;
    }
    return false;
}

// Universal function for cleaning control elements by ID / Универсальная функция очистки элементов управления по ID
function clearFormFields(ids) {
    ids.forEach(id => {
        const element = document.getElementById(id);
        if (!element) return;
        // For a container with radio buttons or checkboxes / Для контейнера с радиокнопками или чекбоксами
        const radioCheckboxes = element.querySelectorAll('input[type="radio"], input[type="checkbox"]');
        if (radioCheckboxes.length > 0) {
            radioCheckboxes.forEach(el => el.checked = false);
            return;
        }
        // For Input / Для Input
        if (element instanceof HTMLInputElement) {
            if (element.type === 'radio' || element.type === 'checkbox') {
                element.checked = false;
            } else {
                element.value = '';
            }
        }
        // For Textarea / Для Textarea
        if (element.tagName === 'TEXTAREA') {
            element.value = '';
        }
        // Fro Select / Для Select
        if (element.tagName === 'SELECT') {
            element.selectedIndex = -1; // Remove all selections / Снимаем все выделения
        }
    });
    // A list may have lost its selection: refresh the buttons that need a selected row
    // Список мог потерять выбор: обновляем кнопки, которым нужна выбранная строка
    updateCheckedDependentButtons();
}

// Function to add the selected tags (one or several) to the list of keywords for tag filtering; the tags that are
// already in the field are skipped
// Функция добавления выбранных тегов (одного или нескольких) в список ключевых слов для фильтра по тегам; теги, которые
// уже есть в поле, пропускаются
function addTagToFilterFromAllTags(selectId, textareaId, separator = ';', newLineSeparator = '\n') {
    // Get the selected values from Select and the current value from Input
    // Получаем выбранные значения из Select и текущее значение из Input
    const selectedTexts = getSelectTexts(selectId);
    const currentValue = getInputValue(textareaId);
    if (selectedTexts.length === 0) {
        console.warn('Nothing selected in select!');
        return;
    }
    // Split by both delimiters to check for duplicates / Разделяем по обоим разделителям для проверки дубликатов
    const existingValues = currentValue ?
        currentValue.split(new RegExp(`[${separator}${newLineSeparator}]`))
            .map(val => val.trim()).filter(val => val) :
        [];
    // Checking which values are not in the field yet / Проверяем, каких значений в поле еще нет
    const newTexts = selectedTexts.filter((text, index) => !existingValues.includes(text)
        && selectedTexts.indexOf(text) === index);
    if (newTexts.length === 0) {
        console.log('The values are already in the field!');
        clearFormFields([selectId]);
        return;
    }
    // Add each value on a new line / Добавляем каждое значение с новой строки
    if (document.getElementById(textareaId)) {
        let newValue = currentValue;
        newTexts.forEach(text => {
            newValue = newValue.trim() ? newValue + newLineSeparator + text + separator : text + separator;
        });
        setInputValue(textareaId, newValue);
    }
    // The selection is used up: clear it (the button becomes disabled until the next selection)
    // Выбор использован: сбрасываем его (кнопка неактивна до следующего выбора)
    clearFormFields([selectId]);
}


// Functions for implementing status bar functionality
// Функции для реализации функциональности строки статуса

// Function for updating the status string. We check the status every 500 ms.
// Функция для обновления строки статуса. Проверяем статус каждые 500мс
// The server returns an empty body if nothing changed since the version we send, so the list is not redrawn
// (an open list does not jump). After a redraw the last (newest) line is selected, so the closed list shows it.
// Сервер возвращает пустое тело, если с отправленной версии ничего не изменилось, поэтому список не перерисовывается
// (открытый список не дергается). После перерисовки выбирается последняя (новая) строка, и закрытый список ее показывает.
let statusVersion = null;
setInterval(() => {
    const url = statusVersion === null ? '/status_output' : `/status_output?since=${statusVersion}`;
    fetch(url)
        .then(response => {
            if (!response.ok) {
                // Not an answer with the messages (e.g. the server is restarting): keep the version, try again
                // Это не ответ с сообщениями (например, сервер перезапускается): версию не трогаем, пробуем снова
                throw new Error(`HTTP ${response.status}`);
            }
            statusVersion = response.headers.get('X-Status-Version');
            return response.json();
        })
        .then(data => {
            if (Object.keys(data).length > 0) {
                updateElementsFromResponse(data);
                const report = document.getElementById('sb_report');
                if (report && report.options.length > 0) {
                    report.selectedIndex = report.options.length - 1;
                }
            }
        })
        .catch(err => console.error('Status bar update failed:', err));
}, 500);


// Functions for working with Telegram message lists and databases
// Функции для работы с Checkbox списков сообщений Telegram и базы данных

// Function to select all checkboxes in the list by container ID
// Функция для установки выделения всех checkbox в списке по ID контейнера
function selectAllCB(selector, counterId) {
    const checkboxes = document.querySelectorAll(selector);
    checkboxes.forEach(cb => cb.checked = true);
    updateCheckboxCounter(selector, counterId);
}

// Function to uncheck all checkboxes in a list by container ID
// Функция для снятия выделения всех checkbox в списке по ID контейнера
function deSelectAllCB(selector, counterId) {
    const checkboxes = document.querySelectorAll(selector);
    checkboxes.forEach(cb => cb.checked = false);
    updateCheckboxCounter(selector, counterId);
}

// Function to invert the selection of all checkboxes in the list by container ID
// Функция для инвертирования выделения всех checkbox в списке по ID контейнера
function invertSelectionCB(selector, counterId) {
    const checkboxes = document.querySelectorAll(selector);
    checkboxes.forEach(cb => cb.checked = !cb.checked);
    updateCheckboxCounter(selector, counterId);
}

// Function to update the counter of selected items and all Checkbox items in the list by selector
// Функция для обновления счетчика выделенных элементов и всех элементов Checkbox в списке по селектору
function updateCheckboxCounter(checkboxSelector, modifyElementId) {
    const allCheckboxes = document.querySelectorAll(checkboxSelector);
    const allCount = allCheckboxes.length;
    const selectedCount = Array.from(allCheckboxes).filter(cb => cb.checked).length;
    const counterElement = document.getElementById(modifyElementId);
    if (counterElement) {
        let counterString;
        if (selectedCount > 0) {
            counterString = `(${selectedCount} / ${allCount})`;
        } else {
            counterString = `(${allCount})`;
        }
        if (counterElement.tagName === 'INPUT' || counterElement.tagName === 'TEXTAREA') {
            counterElement.value = counterString;
        } else {
            counterElement.textContent = counterString;
        }
    } else {
        console.error(`Элемент с ID "${modifyElementId}" не найден.`);
    }
    // The checked items changed: refresh the buttons that act on them / Отмеченные изменились: обновляем кнопки,
    // действующие на них
    updateCheckedDependentButtons();
}

// Function to delete selected messages with confirmation / Функция удаления выделенных сообщений с подтверждением
/**
 * @param {Object} config
 * @param {Array} [config.checkbox_list]
 * @param {string} url
 */
function deleteSelectedButton(config, url) {
    // Count selected elements via config selector / Подсчитываем выделенные элементы через config селектор
    let totalSelected = 0;
    (config.checkbox_list || []).forEach(field => {
        const selected = document.querySelectorAll(`${field.selector}:checked`);
        totalSelected += selected.length;
    });
    if (totalSelected > 0) {
        if (confirm(`Are you sure you want to delete ${totalSelected} messages and their files from disk?\nThis action cannot be undone!`)) {
            pressFormButton(config, url);
        }
    }
}


// Functions for working with notifications
// Функции для работы с уведомлениями

// Simple notification / Простое уведомление
function showMessage(message, type = 'info') {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${type}`;
    messageDiv.textContent = message;
    document.body.appendChild(messageDiv);
    // Auto delete after 3 seconds / Автоудаление через 3 секунды
    setTimeout(() => {
        if (messageDiv.parentNode) {
            messageDiv.parentNode.removeChild(messageDiv);
        }
    }, 3000);
}

// Function for displaying notifications (placeholder, can be replaced with a library)
// Функция для показа уведомлений (заглушка, можно заменить на библиотеку)
function showNotification(message, type = 'info') {
    console.log(`[${type.toUpperCase()}] ${message}`);
}
