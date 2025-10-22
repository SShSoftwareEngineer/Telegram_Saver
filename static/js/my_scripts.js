// Функция реализующая переключение между вкладками
function openTab(evt, tabName) {
    // Скрываем все содержимое вкладок
    const tabContents = document.getElementsByClassName("tab-content");
    for (let i = 0; i < tabContents.length; i++) {
        tabContents[i].style.display = "none";
    }
    // Убираем класс "active" со всех кнопок вкладок
    const tabButtons = document.getElementsByClassName("tab-button");
    for (let i = 0; i < tabButtons.length; i++) {
        tabButtons[i].className = tabButtons[i].className.replace(" active", "");
    }
    // Показываем текущую вкладку и добавляем класс "active" к кнопке
    document.getElementById(tabName).style.display = "block";
    evt.currentTarget.className += " active";
}


// Функции для работы с элементами управления формы по ID

// Получение значения выбранной радиокнопки по ID контейнера
function getRadioValue(identifier) {
    const container = document.getElementById(identifier);
    if (!container) return null;
    const checked = container.querySelector('input[type="radio"]:checked');
    return checked ? checked.value : null;
}

// Получение значения текстового поля или textarea по ID
function getInputValue(id) {
    const input = document.getElementById(id);
    return input ? input.value.trim() : '';
}

// Получение значения выбранного в select по ID
function getSelectValue(id) {
    const select = document.getElementById(id);
    if (!select) return '';
    // Если select с множественным выбором
    if (select.hasAttribute('multiple')) {
        // Возвращаем массив выбранных значений
        const selectedValues = Array.from(select.selectedOptions).map(option => option.value);
        return selectedValues.length > 0 ? selectedValues : '';
    } else {
        // Обычный select - возвращаем одно значение
        return select.value;
    }
}

// Получение текста выбранного в select по ID
function getSelectText(id) {
    const select = document.getElementById(id);
    return select.options[select.selectedIndex].text || '';
}

// Получение значения множественного выбора checkbox группы по ID контейнера
function getCheckboxValues(id) {
    const container = document.getElementById(id);
    if (!container) return [];
    const checkboxes = container.querySelectorAll('input[type="checkbox"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

// Универсальная функция добавления данных формы в FormData с проверкой
function appendIfExists(formData, name, value) {
    if (value === null || value === undefined || value === '') {
        return;
    }
    // Если значение - массив (из multiple select)
    if (Array.isArray(value)) {
        value.forEach(item => formData.append(name, item));
    } else {
        formData.append(name, value);
    }
}

// Универсальная функция сбора данных формы и отправки на сервер
function submitFormData(config, url) {
    const formData = new FormData();
    // Обработка радиокнопок
    (config.radio || []).forEach(field =>
        appendIfExists(formData, field.name, getRadioValue(field.id))
    );
    // Обработка input
    (config.input || []).forEach(field =>
        appendIfExists(formData, field.name, getInputValue(field.id))
    );
    // Обработка select
    (config.select || []).forEach(field =>
        appendIfExists(formData, field.name, getSelectValue(field.id))
    );
    // Обработка checkbox группы, объединенных одним name, обрабатывает массив значений checkbox
    (config.checkbox || []).forEach(field => {
        const values = getCheckboxValues(field.id);
        values.forEach(value => formData.append(field.name, value));
    });
    // Обработка списка ID checkbox (не группы), обрабатывает массив ID чекбоксов
    (config.checkbox_list || []).forEach(field => {
        const selected = document.querySelectorAll(`${field.selector}:checked`);
        const selectedIds = Array.from(selected).map(cb => cb.id);
        selectedIds.forEach(id => {
            formData.append(field.name, id);
        });
    });

    // Отправка запроса и возврат Promise
    return fetch(url, {method: 'POST', body: formData})
        .then(r => r.json())
        .catch(err => {
            console.error('Error:', err);
            console.log('Данные формы:', body);
            throw err;
        });
}

// Универсальная функция обновления элементов по id = ключам из ответа
function updateElementsFromResponse(data) {
    // console.log('updateElementsFromResponse called with:', data);
    Object.keys(data).forEach(key => {
        const element = document.getElementById(key);
        if (!element) {
            console.warn(`❌ Элемент с ID '${key}' НЕ НАЙДЕН на странице!`);
            return;
        }
        // Для checkbox и radio - обновляем checked
        if (element.type === 'checkbox' || element.type === 'radio') {
            element.checked = data[key];
        }
        // Для input/textarea - обновляем value
        else if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
            element.value = data[key];
        }
        // Для остальных элементов - обновляем innerHTML
        else if (typeof data[key] === 'string') {
            element.innerHTML = data[key];
        }
    });
}


// Функция, реализующая нажатие кнопки с конфигурацией элементов формы и URL обработчика
function pressFormButton(config, url) {
    submitFormData(config, url)
        .then(data => updateElementsFromResponse(data))
        .catch(err => {
            console.error('Ошибка при отправке формы:', err);
            alert('Ошибка: ' + err.message);
        });
}

// Функция формирующая GET-запрос для загрузки данных с сервера с заданного URL и обновления элементов
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
            console.log('Получены данные сообщений:', data);
            updateElementsFromResponse(data);
        })
        .catch(err => {
            console.error('Ошибка загрузки сообщений:', err);
            alert('Ошибка загрузки сообщений: ' + err.message);
        });
}

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


// Установка значения элементов по ID

// Установка значения радиокнопки по ID контейнера
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

// Установка значения поля ввода по ID
function setInputValue(id, value) {
    const input = document.getElementById(id);
    if (input) {
        input.value = value;
        return true;
    }
    return false;
}

// Универсальная функция очистки элементов управления по ID
function clearFormFields(ids) {
    ids.forEach(id => {
        const element = document.getElementById(id);
        if (!element) return;
        // Для контейнера с радиокнопками или чекбоксами
        const radioCheckboxes = element.querySelectorAll('input[type="radio"], input[type="checkbox"]');
        if (radioCheckboxes.length > 0) {
            radioCheckboxes.forEach(el => el.checked = false);
            return;
        }
        // Для input
        if (element.tagName === 'INPUT') {
            if (element.type === 'radio' || element.type === 'checkbox') {
                element.checked = false;
            } else {
                element.value = '';
            }
        }
        // Для textarea
        if (element.tagName === 'TEXTAREA') {
            element.value = '';
        }
        // Для select
        if (element.tagName === 'SELECT') {
            element.selectedIndex = -1; // Снимаем все выделения
        }
    });
}


// Функция добавления тега в список ключевых слов для фильтра по тегам
function addTagToFilterFromAllTags(selectId, textareaId, separator = ';', newLineSeparator = '\n') {
    // Получаем выбранное значение из select и текущее значение из input
    const selectedText = getSelectText(selectId);
    const currentValue = getInputValue(textareaId); // работает и для textarea
    if (!selectedText) {
        console.warn('Ничего не выбрано в select');
        return;
    }
    // Разделяем по обоим разделителям для проверки дубликатов
    const existingValues = currentValue ?
        currentValue.split(new RegExp(`[${separator}${newLineSeparator}]`))
            .map(val => val.trim()).filter(val => val) :
        [];
    // Проверяем, есть ли уже такое значение
    if (existingValues.includes(selectedText)) {
        console.log('Значение уже есть в поле');
        return;
    }
    // Добавляем значение с новой строки
    const textareaElement = document.getElementById(textareaId);
    if (textareaElement) {
        if (currentValue.trim()) {
            setInputValue(textareaId, currentValue + newLineSeparator + selectedText + separator);
        } else {
            setInputValue(textareaId, selectedText + separator)
        }
    }
}

// Функции для реализации функциональности строки статуса

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


// Функции для работы с checkbox списков сообщений Telegram и базы данных

// Функция для установки выделения всех checkbox в списке по ID контейнера
function selectAllCB(selector, counterId) {
    const checkboxes = document.querySelectorAll(selector);
    checkboxes.forEach(cb => cb.checked = true);
    updateCheckboxCounter(selector, counterId);
}

// Функция для снятия выделения всех checkbox в списке по ID контейнера
function deSelectAllCB(selector, counterId) {
    const checkboxes = document.querySelectorAll(selector);
    checkboxes.forEach(cb => cb.checked = false);
    updateCheckboxCounter(selector, counterId);
}

// Функция для инвертирования выделения всех checkbox в списке по ID контейнера
function invertSelectionCB(selector, counterId) {
    const checkboxes = document.querySelectorAll(selector);
    checkboxes.forEach(cb => cb.checked = !cb.checked);
    updateCheckboxCounter(selector, counterId);
}

// Функция для обновления счетчика выделенных и всех checkbox в списке по селектору
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

// Функция удаления выделенных сообщений с подтверждением
function deleteSelectedButton(config, url) {
    // Подсчитываем выделенные через config селектор
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


// Функции для работы с уведомлениями

// Простое уведомление
function showMessage(message, type = 'info') {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${type}`;
    messageDiv.textContent = message;
    document.body.appendChild(messageDiv);
    // Автоудаление через 3 секунды
    setTimeout(() => {
        if (messageDiv.parentNode) {
            messageDiv.parentNode.removeChild(messageDiv);
        }
    }, 3000);
}

// Функция для показа уведомлений (заглушка, можно заменить на библиотеку)
function showNotification(message, type = 'info') {
    console.log(`[${type.toUpperCase()}] ${message}`);
}
