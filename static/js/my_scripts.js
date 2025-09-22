// Функция реализующая переключение между вкладками
function openTab(evt, tabName) {
    // Скрываем все содержимое вкладок
    var tabContents = document.getElementsByClassName("tab-content");
    for (var i = 0; i < tabContents.length; i++) {
        tabContents[i].style.display = "none";
    }
    // Убираем класс "active" со всех кнопок вкладок
    var tabButtons = document.getElementsByClassName("tab-button");
    for (var i = 0; i < tabButtons.length; i++) {
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
    // Обработка checkbox групп (массивы значений)
    (config.checkbox || []).forEach(field => {
        const values = getCheckboxValues(field.id);
        values.forEach(value => formData.append(field.name, value));
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
    console.log('updateElementsFromResponse called with:', data);

    Object.keys(data).forEach(key => {
        const element = document.getElementById(key);
        if (!element) {
            console.warn(`❌ Элемент с ID '${key}' НЕ НАЙДЕН на странице!`);
            return;
        }
        if (element && typeof data[key] === 'string') {
            element.innerHTML = data[key];
        } else {
            console.warn(`❌ Data type for ${key} is:`, typeof data[key]);
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
            // Можно показать общую ошибку или не показывать вообще
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

// Функция обработки Checkbox
function handleCheckbox(checkbox, groupInputName, url) {
    const formData = new FormData();
    // Добавляем данные checkbox
    if (checkbox.checked) {
        formData.append(checkbox.name, 'on');
    }
    // Добавляем данные связанного input
    const groupInput = document.querySelector(`input[name="${groupInputName}"]`);
    if (groupInput) {
        formData.append(groupInputName, groupInput.value);
    }
    // Отправляем данные в обработчик
    fetch(url, {
        method: 'POST',
        body: formData
    })
        .then(r => r.json())
        .then(data => {
            console.log('Success checkbox handle:', data);
            updateElementsFromResponse(data); // ← Добавьте эту строку
        })
        .catch(err => {
            console.error('Error checkbox handle:', err);
            checkbox.checked = !checkbox.checked; // Откат при ошибке
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
