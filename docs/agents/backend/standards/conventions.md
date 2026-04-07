# Конвенции: Laravel 12 / PHP 8

## Структура директорий

```
app/
├── Http/
│   ├── Controllers/
│   │   └── Api/
│   │       └── V1/           # Версионированные контроллеры
│   ├── Requests/             # Form Request классы
│   └── Resources/            # API Resource трансформеры
├── Models/                   # Eloquent модели
├── Services/                 # Бизнес-логика
├── Policies/                 # Авторизация
├── Events/                   # События
├── Listeners/                # Обработчики событий
├── Jobs/                     # Очередные задачи
└── Exceptions/               # Кастомные исключения
```

## Именование

| Тип | Конвенция | Пример |
|-----|-----------|--------|
| Модель | PascalCase, ед.ч. | `User`, `ProductCategory` |
| Контроллер | PascalCase + Controller | `UserController` |
| Сервис | PascalCase + Service | `UserService` |
| Form Request | Action + Resource + Request | `StoreUserRequest` |
| Resource | Resource + Resource | `UserResource` |
| Collection | Resource + Collection | `UserCollection` |
| Policy | Resource + Policy | `UserPolicy` |
| Job | глагол + существительное | `SendWelcomeEmail` |
| Event | прошедшее время | `UserRegistered` |

## Модели

```php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\SoftDeletes;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Product extends Model
{
    use SoftDeletes;

    protected $fillable = [
        'name',
        'price',
        'category_id',
        'status',
    ];

    protected $casts = [
        'price' => 'decimal:2',
        'status' => ProductStatus::class, // PHP 8.1 enum
        'settings' => 'array',
    ];

    // Relationships
    public function category(): BelongsTo
    {
        return $this->belongsTo(Category::class);
    }

    public function orders(): HasMany
    {
        return $this->hasMany(Order::class);
    }

    // Scopes
    public function scopeActive($query)
    {
        return $query->where('status', ProductStatus::Active);
    }
}
```

## Контроллеры

```php
<?php

namespace App\Http\Controllers\Api\V1;

use App\Http\Controllers\Controller;
use App\Http\Requests\StoreProductRequest;
use App\Http\Requests\UpdateProductRequest;
use App\Http\Resources\ProductResource;
use App\Services\ProductService;
use App\Models\Product;

class ProductController extends Controller
{
    public function __construct(
        private readonly ProductService $productService
    ) {}

    public function index()
    {
        $products = $this->productService->paginate(request()->all());
        return ProductResource::collection($products);
    }

    public function store(StoreProductRequest $request)
    {
        $product = $this->productService->create($request->validated());
        return response()->json([
            'data' => new ProductResource($product),
            'message' => 'Создан успешно',
        ], 201);
    }

    public function show(Product $product)
    {
        $this->authorize('view', $product);
        return new ProductResource($product);
    }

    public function update(UpdateProductRequest $request, Product $product)
    {
        $this->authorize('update', $product);
        $product = $this->productService->update($product, $request->validated());
        return response()->json([
            'data' => new ProductResource($product),
            'message' => 'Обновлён успешно',
        ]);
    }

    public function destroy(Product $product)
    {
        $this->authorize('delete', $product);
        $this->productService->delete($product);
        return response()->json(['message' => 'Удалён успешно']);
    }
}
```

## Маршруты

```php
// routes/api.php
Route::prefix('v1')->middleware(['auth:sanctum'])->group(function () {

    Route::apiResource('products', ProductController::class);

    // Вложенные ресурсы
    Route::apiResource('categories.products', CategoryProductController::class)
        ->shallow();

    // Нестандартные действия
    Route::post('products/{product}/publish', [ProductController::class, 'publish'])
        ->name('products.publish');
});
```

## PHP 8 возможности

```php
// Constructor promotion
public function __construct(
    private readonly UserService $userService,
    private readonly string $defaultStatus = 'active',
) {}

// Named arguments
$result = $this->service->create(
    name: $request->name,
    status: $request->status ?? 'active',
);

// Match expression
$label = match($status) {
    'active' => 'Активен',
    'inactive' => 'Неактивен',
    default => 'Неизвестно',
};

// Nullsafe operator
$city = $user?->address?->city;

// Enums (PHP 8.1)
enum ProductStatus: string {
    case Active = 'active';
    case Inactive = 'inactive';
}
```
