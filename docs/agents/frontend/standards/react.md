# Конвенции: React

## Структура директорий

```
resources/js/          # или src/
├── api/               # HTTP-клиент и функции запросов
│   ├── client.ts      # Axios / fetch instance
│   └── products.ts
├── components/        # Переиспользуемые компоненты
│   ├── ui/            # Базовые (Button, Input, Modal)
│   ├── forms/
│   └── layout/
├── hooks/             # Кастомные хуки (useProducts, usePagination)
├── pages/             # Страницы (один файл = один роут)
├── store/             # Redux Toolkit или Zustand
│   └── products/
│       ├── slice.ts   # Redux slice
│       └── api.ts     # RTK Query / thunks
├── types/             # TypeScript типы
└── App.tsx            # Точка входа
```

## Именование

| Тип | Конвенция | Пример |
|-----|-----------|--------|
| Компонент | PascalCase | `ProductCard.tsx` |
| Страница | PascalCase + Page | `ProductListPage.tsx` |
| Хук | use + PascalCase | `useProductForm.ts` |
| Redux slice | camelCase | `productsSlice.ts` |
| API-функция | глагол + ресурс | `fetchProducts`, `createProduct` |

## Структура компонента

```tsx
import { useState, useEffect } from 'react'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import { fetchProducts, selectProducts } from '@/store/products/slice'

interface Props {
  categoryId: number
  onSelect?: (id: number) => void
}

export function ProductList({ categoryId, onSelect }: Props) {
  const dispatch = useAppDispatch()
  const { items, isLoading, error } = useAppSelector(selectProducts)

  useEffect(() => {
    dispatch(fetchProducts({ categoryId }))
  }, [categoryId, dispatch])

  if (isLoading) return <Spinner />
  if (error) return <ErrorMessage message={error} />
  if (!items.length) return <EmptyState />

  return (
    <ul>
      {items.map(item => (
        <li key={item.id} onClick={() => onSelect?.(item.id)}>
          {item.name}
        </li>
      ))}
    </ul>
  )
}
```

## Redux Toolkit slice

```typescript
// store/products/slice.ts
import { createSlice, createAsyncThunk } from '@reduxjs/toolkit'
import * as api from '@/api/products'

export const fetchProducts = createAsyncThunk(
  'products/fetchAll',
  async (params: Record<string, unknown>) => {
    const response = await api.fetchProducts(params)
    return response.data.data
  }
)

const productsSlice = createSlice({
  name: 'products',
  initialState: {
    items: [] as Product[],
    isLoading: false,
    error: null as string | null,
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchProducts.pending, (state) => {
        state.isLoading = true
        state.error = null
      })
      .addCase(fetchProducts.fulfilled, (state, action) => {
        state.isLoading = false
        state.items = action.payload
      })
      .addCase(fetchProducts.rejected, (state, action) => {
        state.isLoading = false
        state.error = action.error.message ?? 'Ошибка загрузки'
      })
  },
})

export const selectProducts = (state: RootState) => state.products
export default productsSlice.reducer
```

## Кастомный хук

```typescript
// hooks/useProductForm.ts
import { useState } from 'react'
import { createProduct } from '@/api/products'

export function useProductForm(onSuccess?: () => void) {
  const [isLoading, setIsLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  async function submit(data: CreateProductDto) {
    setIsLoading(true)
    setErrors({})
    try {
      await createProduct(data)
      onSuccess?.()
    } catch (e: any) {
      if (e.response?.status === 422) {
        setErrors(e.response.data.errors)
      }
    } finally {
      setIsLoading(false)
    }
  }

  return { submit, isLoading, errors }
}
```

## Чеклист перед сдачей

- [ ] Только функциональные компоненты (не классовые)
- [ ] Нет прямых API-вызовов в компонентах — только через хуки или store
- [ ] `useEffect` с правильным dependency array
- [ ] Все состояния loading/error/empty обработаны
- [ ] Нет мутаций state напрямую — только через dispatch / setter
- [ ] Формы блокируются во время отправки
- [ ] Нет забытых `console.log`
