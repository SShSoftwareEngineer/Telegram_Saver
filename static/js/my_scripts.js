// Обработчик JSON-ответов от HTMX
// Этот скрипт предназначен для обработки JSON-ответов от HTMX и обновления DOM
document.addEventListener('DOMContentLoaded', function () {

    // Безопасная проверка body
    if (document.body) {

        // Перехватчик JSON-ответов от HTMX
        document.body.addEventListener("htmx:beforeSwap", function (event) {

            // Получаем Content-Type
            let contentType = event.detail.xhr.getResponseHeader("Content-Type");
            console.log("Content-Type:", contentType);

            // Проверяем, что ответ — JSON
            if (contentType && contentType.indexOf("application/json") !== -1) {
                console.log("JSON response detected");
                try {
                    let data = JSON.parse(event.detail.xhr.responseText);
                    console.log("Parsed JSON data:", data);

                    // Проверяем, что это объект
                    if (typeof data !== 'object' || data === null) {
                        console.warn("JSON response is not an object");
                        return;
                    }
                    let updatedCount = 0;

                    // Обновляем элементы по id
                    for (let id in data) {
                        if (data.hasOwnProperty(id)) {
                            let el = document.getElementById(id);
                            if (el) {

                                // Безопасное обновление содержимого
                                if (typeof data[id] === 'string') {
                                    el.innerHTML = data[id];
                                } else {
                                    el.textContent = String(data[id]);
                                }
                                updatedCount++;
                                console.log(`✓ Updated element '${id}'`);
                            } else {
                                console.warn(`✗ Element '${id}' not found in DOM`);
                            }
                        }
                    }
                    console.log(`Updated ${updatedCount} elements`);

                    // Отменяем стандартный swap от HTMX
                    event.detail.shouldSwap = false;
                } catch (error) {
                    console.error("Error processing JSON response:", error);
                    console.log("Raw response:", event.detail.xhr.responseText);

                    // Позволяем HTMX обработать ответ стандартным способом
                }
            }
        });
    } else {
        console.error("document.body is null!");
    }
});


// Дополнительно - логирование всех HTMX событий для отладки
document.body.addEventListener("htmx:afterRequest", function (event) {
    console.log("HTMX request completed:", {
        status: event.detail.xhr.status,
        url: event.detail.pathInfo.requestPath,
        contentType: event.detail.xhr.getResponseHeader("Content-Type")
    });
});


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



// Fill a select element with options from a given data array.
// function FillSelect(selectId, data) {
//     const select = document.getElementById(selectId);
//     // Проверяем, существует ли элемент перед работой с ним
//     if (!select) {
//         console.error(`Элемент с id "${selectId}" не найден.`);
//         return;
//     }
//     // Очищаем список
//     select.innerHTML = '';
//     // Добавляем новые опции
//     data.forEach(item => {
//         const option = document.createElement('option');
//         option.value = item.id;
//         option.textContent = item.name;
//         // Если есть дополнительные данные, сохраняем их в data-атрибуты
//         if (item.data) {
//             for (const key in item.data) {
//                 option.dataset[key] = item.data[key];
//             }
//         }
//         select.appendChild(option);
//     });
// }