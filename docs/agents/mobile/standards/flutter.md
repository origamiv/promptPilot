# Конвенции: Flutter

## Структура директорий

```
mobile/lib/
├── api/                  # HTTP-клиент и репозитории
│   ├── client.dart       # Dio instance с interceptors
│   ├── auth_api.dart
│   └── products_api.dart
├── models/               # Data классы (freezed / json_serializable)
│   └── product.dart
├── providers/            # Riverpod провайдеры (или BLoC)
│   └── products_provider.dart
├── router/               # GoRouter конфигурация
│   └── router.dart
├── screens/              # Экраны (один файл = один экран)
│   ├── auth/
│   └── products/
│       ├── product_list_screen.dart
│       └── product_detail_screen.dart
├── widgets/              # Переиспользуемые виджеты
│   ├── common/           # Базовые (AppButton, AppTextField)
│   └── products/
└── main.dart
```

## Именование

| Тип | Конвенция | Пример |
|-----|-----------|--------|
| Файл | snake_case | `product_list_screen.dart` |
| Класс / виджет | PascalCase | `ProductListScreen` |
| Провайдер | camelCase + Provider | `productsProvider` |
| Метод / переменная | camelCase | `fetchProducts`, `isLoading` |
| Константы | lowerCamelCase | `primaryColor`, `baseUrl` |

## Структура экрана (Riverpod)

```dart
// screens/products/product_list_screen.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/products_provider.dart';
import '../../widgets/products/product_card.dart';

class ProductListScreen extends ConsumerWidget {
  const ProductListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final productsAsync = ref.watch(productsProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Продукты')),
      body: SafeArea(
        child: productsAsync.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(
            child: Text('Ошибка: $e', style: const TextStyle(color: Colors.red)),
          ),
          data: (products) => products.isEmpty
              ? const Center(child: Text('Нет продуктов'))
              : ListView.builder(
                  itemCount: products.length,
                  itemBuilder: (context, index) =>
                      ProductCard(product: products[index]),
                ),
        ),
      ),
    );
  }
}
```

## Экран с формой

```dart
class ProductFormScreen extends ConsumerStatefulWidget {
  const ProductFormScreen({super.key});

  @override
  ConsumerState<ProductFormScreen> createState() => _ProductFormScreenState();
}

class _ProductFormScreenState extends ConsumerState<ProductFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  bool _isLoading = false;

  @override
  void dispose() {
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _isLoading = true);
    try {
      await ref.read(productsProvider.notifier).create(
        name: _nameController.text.trim(),
      );
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Ошибка: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Новый продукт')),
      body: SafeArea(
        child: SingleChildScrollView(
          // resizeToAvoidBottomInset: true (default) — клавиатура не перекрывает
          padding: const EdgeInsets.all(16),
          child: Form(
            key: _formKey,
            child: Column(
              children: [
                TextFormField(
                  controller: _nameController,
                  decoration: const InputDecoration(labelText: 'Название'),
                  validator: (v) => v == null || v.isEmpty ? 'Обязательное поле' : null,
                ),
                const SizedBox(height: 24),
                ElevatedButton(
                  onPressed: _isLoading ? null : _submit,
                  child: _isLoading
                      ? const SizedBox(
                          width: 20, height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Создать'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
```

## Riverpod провайдер

```dart
// providers/products_provider.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../api/products_api.dart';
import '../models/product.dart';

final productsProvider =
    AsyncNotifierProvider<ProductsNotifier, List<Product>>(ProductsNotifier.new);

class ProductsNotifier extends AsyncNotifier<List<Product>> {
  @override
  Future<List<Product>> build() async {
    return _fetch();
  }

  Future<List<Product>> _fetch() async {
    final api = ref.read(productsApiProvider);
    return api.fetchProducts();
  }

  Future<void> create({required String name}) async {
    final api = ref.read(productsApiProvider);
    final newProduct = await api.createProduct(name: name);
    state = AsyncData([...state.value ?? [], newProduct]);
  }
}
```

## Dio API-клиент

```dart
// api/client.dart
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

final dio = Dio(BaseOptions(
  baseUrl: const String.fromEnvironment('API_URL', defaultValue: 'https://api.example.com'),
  connectTimeout: const Duration(seconds: 10),
  receiveTimeout: const Duration(seconds: 30),
  headers: {'Accept': 'application/json'},
));

// Interceptor для Bearer токена
dio.interceptors.add(InterceptorsWrapper(
  onRequest: (options, handler) async {
    const storage = FlutterSecureStorage();
    final token = await storage.read(key: 'auth_token');
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    return handler.next(options);
  },
  onError: (e, handler) {
    if (e.response?.statusCode == 401) {
      // Редирект на логин
    }
    return handler.next(e);
  },
));
```

## GoRouter навигация

```dart
// router/router.dart
import 'package:go_router/go_router.dart';

final router = GoRouter(
  routes: [
    GoRoute(
      path: '/',
      builder: (context, state) => const ProductListScreen(),
    ),
    GoRoute(
      path: '/products/:id',
      builder: (context, state) => ProductDetailScreen(
        productId: int.parse(state.pathParameters['id']!),
      ),
    ),
  ],
);
```

## Чеклист перед сдачей

- [ ] Dart null safety — нет `!` без уверенности, нет `dynamic`
- [ ] Логика в провайдерах / BLoC, не в виджетах
- [ ] `SafeArea` на корневых экранах
- [ ] `Scaffold` с `resizeToAvoidBottomInset: true` (по умолчанию) на экранах с формами
- [ ] `dispose()` для всех контроллеров
- [ ] Токены в `flutter_secure_storage`, не в SharedPreferences
- [ ] `mounted` проверка после async операций в State
- [ ] Нет забытых `print()`
