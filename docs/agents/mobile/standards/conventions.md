# Конвенции: React Native

## Структура директорий

```
mobile/
├── src/
│   ├── api/              # HTTP-клиент и функции запросов
│   │   ├── client.ts     # Axios instance
│   │   └── products.ts
│   ├── components/       # Переиспользуемые компоненты
│   │   ├── ui/           # Базовые (Button, Input, Card)
│   │   └── forms/        # Компоненты форм
│   ├── navigation/       # React Navigation конфигурация
│   │   ├── RootNavigator.tsx
│   │   └── types.ts      # ParamList типы
│   ├── screens/          # Экраны приложения
│   ├── stores/           # Zustand stores
│   ├── hooks/            # Кастомные хуки
│   ├── types/            # TypeScript типы
│   └── utils/            # Утилиты
├── android/
├── ios/
├── package.json
└── tsconfig.json
```

## Zustand Store

```typescript
// stores/product.ts
import { create } from 'zustand'
import * as api from '@/api/products'
import type { Product } from '@/types'

interface ProductStore {
  items: Product[]
  isLoading: boolean
  error: string | null
  fetchAll: () => Promise<void>
  create: (data: Omit<Product, 'id'>) => Promise<Product>
}

export const useProductStore = create<ProductStore>((set) => ({
  items: [],
  isLoading: false,
  error: null,

  fetchAll: async () => {
    set({ isLoading: true, error: null })
    try {
      const response = await api.fetchProducts()
      set({ items: response.data.data })
    } catch {
      set({ error: 'Не удалось загрузить' })
    } finally {
      set({ isLoading: false })
    }
  },

  create: async (data) => {
    const response = await api.createProduct(data)
    const newItem = response.data.data
    set((state) => ({ items: [...state.items, newItem] }))
    return newItem
  },
}))
```

## Стили

```typescript
// Всегда StyleSheet.create(), никогда inline объекты
const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#FFFFFF',
  },
  header: {
    fontSize: 24,
    fontWeight: '700',
    color: '#1A1A1A',
    marginBottom: 16,
  },
  // Адаптивные отступы
  content: {
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
})
```

## Типы навигации

```typescript
// navigation/types.ts
export type RootStackParamList = {
  Home: undefined
  ProductList: undefined
  ProductDetail: { productId: number }
  CreateProduct: { categoryId?: number }
}

// Типизированный useNavigation
import { NativeStackNavigationProp } from '@react-navigation/native-stack'
type NavigationProp = NativeStackNavigationProp<RootStackParamList>
```
