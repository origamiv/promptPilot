# Шаблон Laravel миграции

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::create('table_name', function (Blueprint $table) {
            // Primary key
            $table->id(); // BIGINT AUTO_INCREMENT

            // Foreign keys (создаются ДО других полей для читаемости)
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            // $table->foreignId('category_id')->nullable()->constrained()->nullOnDelete();

            // Строковые поля
            $table->string('name');           // VARCHAR(255)
            $table->string('slug')->unique(); // VARCHAR(255) UNIQUE
            $table->text('description')->nullable();

            // Числа
            $table->decimal('price', 10, 2)->default(0);
            $table->integer('quantity')->default(0);
            $table->bigInteger('views_count')->default(0);

            // Булевы
            $table->boolean('is_active')->default(true);

            // JSON (JSONB для PostgreSQL — быстрее для запросов)
            $table->jsonb('settings')->nullable();
            $table->jsonb('meta')->nullable();

            // Статус (используй string с фиксированным набором или PostgreSQL enum)
            $table->string('status', 20)->default('active');

            // Даты
            $table->date('published_date')->nullable();
            $table->timestampTz('scheduled_at')->nullable();

            // Системные поля (всегда последними)
            $table->timestamps();  // created_at, updated_at
            $table->softDeletes(); // deleted_at (для бизнес-сущностей)

            // Индексы (после объявления полей)
            $table->index('status');
            $table->index('user_id'); // обычно создаётся constrained(), но явно — понятнее
            $table->index(['status', 'created_at']); // составной для фильтрации + сортировки
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('table_name');
    }
};
```

## Шаблон миграции изменения таблицы

```php
public function up(): void
{
    Schema::table('existing_table', function (Blueprint $table) {
        // Добавить поле
        $table->string('new_field')->nullable()->after('existing_field');

        // Добавить foreign key
        $table->foreignId('new_id')->nullable()->after('other_id')
            ->constrained('other_table')->nullOnDelete();

        // Добавить индекс
        $table->index('new_field');

        // Изменить поле (требует doctrine/dbal)
        $table->string('name', 500)->change();
    });
}

public function down(): void
{
    Schema::table('existing_table', function (Blueprint $table) {
        // Удалить в обратном порядке
        $table->dropIndex(['new_field']);
        $table->dropForeign(['new_id']);
        $table->dropColumn(['new_field', 'new_id']);
    });
}
```
