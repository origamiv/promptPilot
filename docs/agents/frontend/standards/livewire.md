# Конвенции: Laravel Livewire 3

## Структура файлов

```
app/Livewire/          # PHP-классы компонентов
├── Products/
│   ├── ProductList.php
│   ├── ProductForm.php
│   └── ProductCard.php
└── Orders/
    └── OrderList.php

resources/views/livewire/  # Blade-шаблоны компонентов
├── products/
│   ├── product-list.blade.php
│   ├── product-form.blade.php
│   └── product-card.blade.php
└── orders/
    └── order-list.blade.php
```

## Структура компонента

```php
<?php
// app/Livewire/Products/ProductForm.php

namespace App\Livewire\Products;

use App\Models\Product;
use Livewire\Component;
use Livewire\Attributes\Rule;

class ProductForm extends Component
{
    public ?int $productId = null;

    #[Rule('required|string|max:255')]
    public string $name = '';

    #[Rule('required|numeric|min:0')]
    public float $price = 0;

    #[Rule('nullable|string')]
    public ?string $description = null;

    // Инициализация при передаче ID
    public function mount(?int $productId = null): void
    {
        if ($productId) {
            $product = Product::findOrFail($productId);
            $this->name = $product->name;
            $this->price = $product->price;
            $this->description = $product->description;
        }
        $this->productId = $productId;
    }

    public function save(): void
    {
        $this->validate();

        $data = [
            'name'        => $this->name,
            'price'       => $this->price,
            'description' => $this->description,
        ];

        if ($this->productId) {
            Product::findOrFail($this->productId)->update($data);
        } else {
            Product::create($data);
        }

        session()->flash('success', 'Сохранено');
        $this->dispatch('product-saved');
    }

    public function render()
    {
        return view('livewire.products.product-form');
    }
}
```

```blade
{{-- resources/views/livewire/products/product-form.blade.php --}}
<div>
    @if (session()->has('success'))
        <div class="alert alert-success">{{ session('success') }}</div>
    @endif

    <form wire:submit="save">
        <div>
            <label>Название</label>
            <input type="text" wire:model="name">
            @error('name') <span class="error">{{ $message }}</span> @enderror
        </div>

        <div>
            <label>Цена</label>
            <input type="number" wire:model="price" step="0.01">
            @error('price') <span class="error">{{ $message }}</span> @enderror
        </div>

        <button type="submit" wire:loading.attr="disabled">
            <span wire:loading.remove>Сохранить</span>
            <span wire:loading>Сохранение...</span>
        </button>
    </form>
</div>
```

## Список с поиском и пагинацией

```php
use Livewire\WithPagination;

class ProductList extends Component
{
    use WithPagination;

    public string $search = '';
    public string $sortBy = 'created_at';
    public string $sortDir = 'desc';

    // Сбрасывать пагинацию при изменении поиска
    public function updatingSearch(): void
    {
        $this->resetPage();
    }

    public function render()
    {
        $products = Product::query()
            ->when($this->search, fn ($q) => $q->where('name', 'like', "%{$this->search}%"))
            ->orderBy($this->sortBy, $this->sortDir)
            ->paginate(20);

        return view('livewire.products.product-list', compact('products'));
    }
}
```

## Alpine.js для клиентской интерактивности

Livewire для серверной логики, Alpine.js для чисто UI-поведения:

```blade
{{-- Дропдаун без обращения к серверу --}}
<div x-data="{ open: false }">
    <button @click="open = !open">Меню</button>
    <ul x-show="open" @click.outside="open = false">
        <li>Пункт 1</li>
        <li>Пункт 2</li>
    </ul>
</div>

{{-- Подтверждение перед серверным действием --}}
<button
    x-on:click="$wire.delete({{ $product->id }})"
    x-confirm="Удалить продукт?"
>
    Удалить
</button>
```

## Чеклист перед сдачей

- [ ] Один компонент = один экран или виджет, не монолит
- [ ] Все поля формы имеют `#[Rule]` атрибуты или `rules()`
- [ ] Кнопка submit: `wire:loading.attr="disabled"` + текст загрузки
- [ ] `resetPage()` при изменении фильтров/поиска (если есть пагинация)
- [ ] Чисто клиентская интерактивность (дропдауны, аккордеоны) — через Alpine.js
- [ ] Flash-сообщения об успехе/ошибке
- [ ] Авторизация через `$this->authorize()` или Gate в методах
- [ ] Тяжёлые операции через `wire:loading` чтобы пользователь видел прогресс
