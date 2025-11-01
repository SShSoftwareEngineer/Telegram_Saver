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

// Retrieving the text selected in select by ID / Получение по ID текста, выбранного в select
function getSelectText(id) {
    /** @type {HTMLSelectElement} */
    const select = document.getElementById(id);
    return select?.options[select.selectedIndex]?.text || '';
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
function submitFormData(config, url) {
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

    // Sending a request and returning a Promise / Отправка запроса и возврат Promise
    return fetch(url, {method: 'POST', body: formData})
        .then(r => r.json())
        .catch(err => {
            console.error('Error:', err);
            console.log('Form data:', formData);
            throw err;
        });
}

// Universal function for updating elements by id = keys from the response
// Универсальная функция обновления элементов по id = ключам из ответа
function updateElementsFromResponse(data) {
    Object.keys(data).forEach(key => {
        /** @type {HTMLElement} */
        const element = document.getElementById(key);
        if (!element) {
            console.warn(`❌ Элемент с ID '${key}' НЕ НАЙДЕН на странице!`);
            return;
        }
        // For checkboxes and radio buttons, update checked / Для checkbox и radio - обновляем checked
        if (element instanceof HTMLInputElement && (element.type === 'checkbox' || element.type === 'radio')) {
            element.checked = data[key];
        }
        // For input and textarea - update value / Для input and textarea - обновляем value
        else if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
            element.value = data[key];
        }
        // For the other elements, update innerHTML / Для остальных элементов - обновляем innerHTML
        else if (typeof data[key] === 'string') {
            element.innerHTML = data[key];
        }
    });
}

// Function that implements button press, with configuration of form elements and URL handler
// Функция, реализующая нажатие кнопки, с конфигурацией элементов формы и URL обработчика
function pressFormButton(config, url) {
    submitFormData(config, url)
        .then(data => updateElementsFromResponse(data))
        .catch(err => {
            console.error('Error sending form:', err);
            alert('Error: ' + err.message);
        });
}

// Function that generates a GET request to download data from the server at a specified URL and to update elements
// Функция, формирующая GET-запрос для загрузки данных с сервера с заданного URL и для обновления элементов
function loadURL(url) {
    fetch(url, {
        method: 'GET',
        headers: {
            'X-Requested-With': 'XMLHttpRequest' // Указываем, что это AJAX
        }
    })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Message data received:', data);
            updateElementsFromResponse(data);
        })
        .catch(err => {
            console.error('Error loading messages:', err);
            alert('Error loading messages: ' + err.message);
        });
}

// Function that calls the handler and updates elements by ID according to the handler's response
// Функция, вызывающая обработчик и обновляющая элементы по ID в соответствии с ответом обработчика
function callHandler(url) {
    fetch(url, {
        method: 'POST'
    })
        .then(r => r.json())
        .then(data => {
            updateElementsFromResponse(data);
        })
        .catch(err => {
            console.error('Error:', err);
        });
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
}

// Function to add a tag to the list of keywords for tag filtering
// Функция добавления тега в список ключевых слов для фильтра по тегам
function addTagToFilterFromAllTags(selectId, textareaId, separator = ';', newLineSeparator = '\n') {
    // Get the selected value from Select and the current value from Input
    // Получаем выбранное значение из Select и текущее значение из Input
    const selectedText = getSelectText(selectId);
    const currentValue = getInputValue(textareaId);
    if (!selectedText) {
        console.warn('Nothing selected in select!');
        return;
    }
    // Split by both delimiters to check for duplicates / Разделяем по обоим разделителям для проверки дубликатов
    const existingValues = currentValue ?
        currentValue.split(new RegExp(`[${separator}${newLineSeparator}]`))
            .map(val => val.trim()).filter(val => val) :
        [];
    // Checking whether such a value already exists / Проверяем, есть ли уже такое значение
    if (existingValues.includes(selectedText)) {
        console.log('The value is already in the field!');
        return;
    }
    // Add the value on a new line / Добавляем значение с новой строки
    const textareaElement = document.getElementById(textareaId);
    if (textareaElement) {
        if (currentValue.trim()) {
            setInputValue(textareaId, currentValue + newLineSeparator + selectedText + separator);
        } else {
            setInputValue(textareaId, selectedText + separator)
        }
    }
}


// Functions for implementing status bar functionality
// Функции для реализации функциональности строки статуса

// Function for updating the status string. We check the status every 500 ms.
// Функция для обновления строки статуса. Проверяем статус каждые 500мс
setInterval(() => {
    fetch('/status_output')
        .then(response => response.json())
        .then(data => {
            if (Object.keys(data).length > 0) {
                updateElementsFromResponse(data);
            }
        });
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
        if (confirm(`Are you sure you want to delete ${totalSelected} messages?\nThis action cannot be undone!`)) {
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
