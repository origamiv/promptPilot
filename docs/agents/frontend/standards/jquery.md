# Конвенции: jQuery

## Структура файлов

```
public/js/          # или resources/js/
├── api.js          # Централизованный слой AJAX-запросов
├── utils.js        # Хелперы (форматирование, валидация)
├── pages/          # Логика конкретных страниц
│   ├── products.js
│   └── orders.js
└── components/     # Переиспользуемые UI-блоки
    ├── modal.js
    └── datatable.js
```

## Принципы организации кода

### Модульный паттерн — один файл = один модуль
```javascript
// pages/products.js
const ProductsPage = (function ($) {
  'use strict'

  // Приватные переменные
  const $table = null
  const $form = null

  // Инициализация
  function init() {
    bindEvents()
    loadProducts()
  }

  // Привязка событий
  function bindEvents() {
    $(document).on('click', '.btn-delete-product', handleDelete)
    $('#product-form').on('submit', handleFormSubmit)
  }

  // Обработчики событий
  function handleDelete(e) {
    e.preventDefault()
    const id = $(this).data('id')
    if (confirm('Удалить продукт?')) {
      deleteProduct(id)
    }
  }

  async function handleFormSubmit(e) {
    e.preventDefault()
    const $btn = $(this).find('[type=submit]')
    $btn.prop('disabled', true)
    try {
      await saveProduct($(this).serialize())
      showSuccess('Сохранено')
    } catch (err) {
      showError(err)
    } finally {
      $btn.prop('disabled', false)
    }
  }

  // Публичный API
  return { init }
})(jQuery)

$(document).ready(() => ProductsPage.init())
```

## Централизованный API-слой

```javascript
// api.js
const Api = (function ($) {
  'use strict'

  const BASE_URL = '/api/v1'

  // Добавляем CSRF и Authorization ко всем запросам
  $.ajaxSetup({
    headers: {
      'X-CSRF-TOKEN': $('meta[name="csrf-token"]').attr('content'),
      'Accept': 'application/json',
    },
  })

  function request(method, url, data) {
    return $.ajax({
      method,
      url: BASE_URL + url,
      data: data ? JSON.stringify(data) : undefined,
      contentType: 'application/json',
    }).then(
      (response) => response,
      (xhr) => {
        const msg = xhr.responseJSON?.message || 'Ошибка сервера'
        if (xhr.status === 401) window.location.href = '/login'
        return Promise.reject({ status: xhr.status, message: msg, errors: xhr.responseJSON?.errors })
      }
    )
  }

  return {
    get:    (url, params) => $.ajax({ method: 'GET', url: BASE_URL + url, data: params }),
    post:   (url, data)   => request('POST', url, data),
    patch:  (url, data)   => request('PATCH', url, data),
    delete: (url)         => request('DELETE', url),
  }
})(jQuery)
```

## Работа с DOM

```javascript
// Кешировать селекторы — не обращаться к DOM повторно
const $modal = $('#product-modal')
const $form = $modal.find('form')
const $submitBtn = $form.find('[type=submit]')

// Показать/скрыть с loading
function showLoading($btn) {
  $btn.prop('disabled', true).data('original-text', $btn.text()).text('Загрузка...')
}
function hideLoading($btn) {
  $btn.prop('disabled', false).text($btn.data('original-text'))
}

// Показ ошибок валидации (422)
function showValidationErrors(errors) {
  $.each(errors, function (field, messages) {
    const $field = $(`[name="${field}"]`)
    $field.addClass('is-invalid')
    $field.next('.invalid-feedback').text(messages[0])
  })
}

// Очистить ошибки перед повторной отправкой
function clearErrors() {
  $('.is-invalid').removeClass('is-invalid')
  $('.invalid-feedback').text('')
}
```

## Чеклист перед сдачей

- [ ] Вся логика в JS-файлах, не inline в HTML (`onclick=...`)
- [ ] Нет `$('...')` вызовов внутри цикла — кешировать селекторы
- [ ] Все AJAX-запросы через централизованный `Api` объект
- [ ] CSRF-токен добавлен во все не-GET запросы
- [ ] Кнопки блокируются во время запроса
- [ ] Ошибки 422 отображаются рядом с полями
- [ ] 401 редиректит на страницу логина
- [ ] Нет забытых `console.log`
- [ ] Нет `eval()` и `innerHTML` с пользовательскими данными (XSS)
