// main.js - БЕЗ перехвата форм!

document.addEventListener('DOMContentLoaded', function() {
    // Авто-скрытие алертов через 5 секунд
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });

    // Форматирование телефона (только визуальное, не блокирует отправку)
    const phoneInputs = document.querySelectorAll('input[type="tel"]');
    phoneInputs.forEach(input => {
        input.addEventListener('input', function(e) {
            let value = e.target.value.replace(/\D/g, '');

            if (value.startsWith('8')) {
                value = '7' + value.slice(1);
            }

            if (value.length > 0) {
                if (value.length <= 1) {
                    value = '+' + value;
                } else if (value.length <= 4) {
                    value = '+' + value[0] + ' (' + value.slice(1);
                } else if (value.length <= 7) {
                    value = '+' + value[0] + ' (' + value.slice(1, 4) + ') ' + value.slice(4);
                } else if (value.length <= 9) {
                    value = '+' + value[0] + ' (' + value.slice(1, 4) + ') ' + value.slice(4, 7) + '-' + value.slice(7);
                } else {
                    value = '+' + value[0] + ' (' + value.slice(1, 4) + ') ' + value.slice(4, 7) + '-' + value.slice(7, 9) + '-' + value.slice(9, 11);
                }
            }

            e.target.value = value;
        });
    });
});
// Подсветка активного пункта нижней навигации при клике
document.addEventListener('DOMContentLoaded', function() {
    const bottomNavItems = document.querySelectorAll('.bottom-nav-item');

    bottomNavItems.forEach(item => {
        item.addEventListener('click', function() {
            // Убираем активный класс у всех
            bottomNavItems.forEach(i => i.classList.remove('active'));
            // Добавляем текущему
            this.classList.add('active');
        });
    });

    // Авто-скрытие алертов через 5 секунд
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });
});