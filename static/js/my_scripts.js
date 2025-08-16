// Fill a select element with options from a given data array.

function FillSelect(selectId, data) {
    const select = document.getElementById(selectId);
    // Проверяем, существует ли элемент перед работой с ним
    if (!select) {
        console.error(`Элемент с id "${selectId}" не найден.`);
        return;
    }
    // Очищаем список
    select.innerHTML = '';
    // Добавляем новые опции
    data.forEach(item => {
        const option = document.createElement('option');
        option.value = item.id;
        option.textContent = item.name;
        // Если есть дополнительные данные, сохраняем их в data-атрибуты
        if (item.data) {
            for (const key in item.data) {
                option.dataset[key] = item.data[key];
            }
        }
        select.appendChild(option);
    });
}