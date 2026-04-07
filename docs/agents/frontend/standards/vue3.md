# Конвенции: Vue.js 3

## Структура директорий

```
resources/js/
├── api/                  # HTTP-клиент и функции запросов
│   ├── client.ts         # Axios instance с interceptors
│   ├── auth.ts
│   └── products.ts
├── components/           # Переиспользуемые компоненты
│   ├── ui/               # Базовые UI компоненты (Button, Input, Modal)
│   ├── forms/            # Компоненты форм
│   └── layout/           # Шапка, сайдбар, футер
├── composables/          # Переиспользуемая логика (useForm, usePagination)
├── pages/                # Страницы (один файл = один маршрут)
├── router/               # Vue Router конфигурация
│   └── index.ts
├── stores/               # Pinia stores
├── types/                # TypeScript типы и интерфейсы
└── app.ts                # Точка входа
```

## Именование

| Тип | Конвенция | Пример |
|-----|-----------|--------|
| Компонент | PascalCase | `ProductCard.vue` |
| Страница | PascalCase + Page | `ProductListPage.vue` |
| Composable | use + PascalCase | `useProductForm.ts` |
| Store | use + PascalCase + Store | `useProductStore.ts` |
| Тип/Интерфейс | PascalCase | `Product`, `CreateProductDto` |
| API-функция | глагол + ресурс | `fetchProducts`, `createProduct` |

## Структура компонента

```vue
<script setup lang="ts">
// 1. Импорты Vue
import { ref, computed, watch, onMounted } from 'vue'

// 2. Импорты сторонних библиотек
import { useRoute } from 'vue-router'

// 3. Импорты проекта
import { useProductStore } from '@/stores/product'
import type { Product } from '@/types'

// 4. Props и Emits
interface Props {
  modelValue: Product | null
  disabled?: boolean
}

interface Emits {
  (e: 'update:modelValue', value: Product): void
  (e: 'save'): void
}

const props = withDefaults(defineProps<Props>(), { disabled: false })
const emit = defineEmits<Emits>()

// 5. Composables и stores
const store = useProductStore()
const route = useRoute()

// 6. Реактивные данные
const isLoading = ref(false)
const error = ref<string | null>(null)

// 7. Computed
const hasData = computed(() => props.modelValue !== null)

// 8. Методы
async function handleSave() {
  isLoading.value = true
  error.value = null
  try {
    await store.save(props.modelValue!)
    emit('save')
  } catch (e) {
    error.value = 'Не удалось сохранить'
  } finally {
    isLoading.value = false
  }
}

// 9. Lifecycle
onMounted(async () => {
  await store.fetchAll()
})
</script>

<template>
  <div v-if="isLoading">Загрузка...</div>
  <div v-else-if="error">{{ error }}</div>
  <div v-else-if="hasData">{{ modelValue?.name }}</div>
  <div v-else>Нет данных</div>
</template>
```

## Pinia Store

```typescript
// stores/product.ts
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as api from '@/api/products'
import type { Product } from '@/types'

export const useProductStore = defineStore('product', () => {
  const items = ref<Product[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  const getById = computed(() => (id: number) =>
    items.value.find(item => item.id === id)
  )

  async function fetchAll(params?: Record<string, unknown>) {
    isLoading.value = true
    error.value = null
    try {
      const response = await api.fetchProducts(params)
      items.value = response.data.data
    } catch (e) {
      error.value = 'Не удалось загрузить'
      throw e
    } finally {
      isLoading.value = false
    }
  }

  async function create(data: Omit<Product, 'id'>) {
    const response = await api.createProduct(data)
    items.value.push(response.data.data)
    return response.data.data
  }

  return { items, isLoading, error, getById, fetchAll, create }
})
```

## API-клиент

```typescript
// api/products.ts
import axios from '@/api/client'
import type { Product, CreateProductDto } from '@/types'

export const fetchProducts = (params?: Record<string, unknown>) =>
  axios.get<{ data: Product[] }>('/api/v1/products', { params })

export const createProduct = (data: CreateProductDto) =>
  axios.post<{ data: Product }>('/api/v1/products', data)

export const updateProduct = (id: number, data: Partial<CreateProductDto>) =>
  axios.patch<{ data: Product }>(`/api/v1/products/${id}`, data)

export const deleteProduct = (id: number) =>
  axios.delete(`/api/v1/products/${id}`)
```

## Чеклист перед сдачей

- [ ] Нет `any` в TypeScript без крайней необходимости
- [ ] Нет прямых axios-вызовов в компонентах
- [ ] Все асинхронные операции имеют loading/error состояния
- [ ] Нет забытых `console.log`
- [ ] Формы блокируются во время отправки
- [ ] Ошибки 422 отображаются рядом с полями
