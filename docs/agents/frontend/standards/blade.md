# Конвенции: Laravel Blade

## Структура директорий

```
resources/views/
├── layouts/               # Базовые layouts
│   ├── app.blade.php      # Основной layout (авторизованные)
│   ├── guest.blade.php    # Layout для гостей
│   └── admin.blade.php    # Layout для админки
├── components/            # Анонимные компоненты
│   ├── button.blade.php
│   ├── input.blade.php
│   ├── modal.blade.php
│   └── table/
│       ├── index.blade.php
│       └── row.blade.php
├── products/              # Папка ресурса
│   ├── index.blade.php
│   ├── create.blade.php
│   ├── edit.blade.php
│   └── show.blade.php
└── partials/              # Включаемые фрагменты
    ├── flash-messages.blade.php
    └── pagination.blade.php
```

## Layouts

```blade
{{-- resources/views/layouts/app.blade.php --}}
<!DOCTYPE html>
<html lang="{{ str_replace('_', '-', app()->getLocale()) }}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>@yield('title', config('app.name'))</title>
    @vite(['resources/css/app.css', 'resources/js/app.js'])
    @stack('styles')
</head>
<body>
    @include('partials.flash-messages')
    <main>
        @yield('content')
    </main>
    @stack('scripts')
</body>
</html>
```

```blade
{{-- Страница --}}
@extends('layouts.app')

@section('title', 'Продукты')

@section('content')
    <h1>Продукты</h1>
    @include('products._table', ['products' => $products])
@endsection

@push('scripts')
    <script src="{{ asset('js/pages/products.js') }}"></script>
@endpush
```

## Анонимные компоненты

```blade
{{-- resources/views/components/input.blade.php --}}
@props([
    'label' => null,
    'error' => null,
    'type' => 'text',
])

<div class="form-group">
    @if ($label)
        <label class="form-label">{{ $label }}</label>
    @endif
    <input
        type="{{ $type }}"
        {{ $attributes->merge(['class' => 'form-control' . ($error ? ' is-invalid' : '')]) }}
    >
    @if ($error)
        <div class="invalid-feedback">{{ $error }}</div>
    @endif
</div>
```

```blade
{{-- Использование --}}
<x-input
    label="Название"
    name="name"
    :value="old('name', $product->name)"
    :error="$errors->first('name')"
/>
```

## Формы

```blade
{{-- Создание --}}
<form action="{{ route('products.store') }}" method="POST">
    @csrf
    <x-input label="Название" name="name" :value="old('name')" :error="$errors->first('name')" />
    <x-input label="Цена" name="price" type="number" :value="old('price')" :error="$errors->first('price')" />
    <button type="submit">Создать</button>
</form>

{{-- Редактирование --}}
<form action="{{ route('products.update', $product) }}" method="POST">
    @csrf
    @method('PATCH')
    <x-input label="Название" name="name" :value="old('name', $product->name)" :error="$errors->first('name')" />
    <button type="submit">Сохранить</button>
</form>

{{-- Удаление --}}
<form action="{{ route('products.destroy', $product) }}" method="POST"
      onsubmit="return confirm('Удалить?')">
    @csrf
    @method('DELETE')
    <button type="submit">Удалить</button>
</form>
```

## Flash-сообщения

```blade
{{-- resources/views/partials/flash-messages.blade.php --}}
@if (session('success'))
    <div class="alert alert-success">{{ session('success') }}</div>
@endif

@if (session('error'))
    <div class="alert alert-danger">{{ session('error') }}</div>
@endif

@if ($errors->any())
    <div class="alert alert-danger">
        <ul class="mb-0">
            @foreach ($errors->all() as $error)
                <li>{{ $error }}</li>
            @endforeach
        </ul>
    </div>
@endif
```

## Авторизация в шаблонах

```blade
@auth
    <a href="{{ route('profile') }}">Профиль</a>
@endauth

@guest
    <a href="{{ route('login') }}">Войти</a>
@endguest

@can('update', $product)
    <a href="{{ route('products.edit', $product) }}">Редактировать</a>
@endcan

@role('admin')
    <a href="{{ route('admin.dashboard') }}">Админка</a>
@endrole
```

## Чеклист перед сдачей

- [ ] `@csrf` во всех формах (POST/PATCH/DELETE)
- [ ] `@method('PATCH')` / `@method('DELETE')` для не-POST методов
- [ ] Нет бизнес-логики в шаблонах — только отображение переданных данных
- [ ] `old('field', $model->field)` для сохранения значений при ошибке
- [ ] Ошибки валидации отображаются рядом с полями через `$errors->first('field')`
- [ ] Переиспользуемые блоки — анонимные компоненты в `resources/views/components/`
- [ ] Flash-сообщения подключены в layout
- [ ] Нет пользовательских данных без `{{ }}` (всегда экранировать, XSS)
- [ ] Использован `{!! !!}` только для заведомо безопасного HTML
