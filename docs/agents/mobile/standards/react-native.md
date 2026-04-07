# Конвенции: React Native

## Структура директорий

```
mobile/src/
├── api/                  # HTTP-клиент и функции запросов
│   ├── client.ts         # Axios instance с interceptors
│   ├── auth.ts
│   └── products.ts
├── components/           # Переиспользуемые компоненты
│   ├── ui/               # Базовые (Button, Input, Modal)
│   └── layout/
├── hooks/                # Кастомные хуки
├── navigation/           # React Navigation стеки и табы
│   ├── RootNavigator.tsx
│   └── types.ts
├── screens/              # Экраны (один файл = один экран)
│   ├── auth/
│   └── products/
├── stores/               # Zustand stores
├── types/                # TypeScript типы
└── utils/                # Хелперы
```

## Именование

| Тип | Конвенция | Пример |
|-----|-----------|--------|
| Экран | PascalCase + Screen | `ProductListScreen.tsx` |
| Компонент | PascalCase | `ProductCard.tsx` |
| Store | use + PascalCase + Store | `useProductStore.ts` |
| Хук | use + PascalCase | `useProductForm.ts` |
| API-функция | глагол + ресурс | `fetchProducts`, `createProduct` |

## Структура экрана

```typescript
import React, { useEffect } from 'react'
import {
  View, FlatList, Text, ActivityIndicator,
  StyleSheet, SafeAreaView, KeyboardAvoidingView, Platform,
} from 'react-native'
import { useProductStore } from '@/stores/product'
import { ProductCard } from '@/components/ProductCard'
import type { NativeStackScreenProps } from '@react-navigation/native-stack'
import type { RootStackParamList } from '@/navigation/types'

type Props = NativeStackScreenProps<RootStackParamList, 'ProductList'>

export function ProductListScreen({ navigation }: Props) {
  const { items, isLoading, error, fetchAll } = useProductStore()

  useEffect(() => {
    fetchAll()
  }, [])

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
      </View>
    )
  }

  if (error) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>{error}</Text>
      </View>
    )
  }

  return (
    <SafeAreaView style={styles.container}>
      <FlatList
        data={items}
        keyExtractor={(item) => item.id.toString()}
        renderItem={({ item }) => (
          <ProductCard
            product={item}
            onPress={() => navigation.navigate('ProductDetail', { productId: item.id })}
          />
        )}
        ListEmptyComponent={<Text style={styles.empty}>Нет продуктов</Text>}
      />
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  errorText: { color: '#EF4444', textAlign: 'center', padding: 16 },
  empty: { textAlign: 'center', color: '#9CA3AF', padding: 32 },
})
```

## Экран с формой

```typescript
import { KeyboardAvoidingView, Platform, ScrollView } from 'react-native'

export function ProductFormScreen() {
  return (
    <SafeAreaView style={{ flex: 1 }}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
      >
        <ScrollView keyboardShouldPersistTaps="handled">
          {/* поля формы */}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  )
}
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
  fetchAll: (params?: Record<string, unknown>) => Promise<void>
  create: (data: Omit<Product, 'id'>) => Promise<Product>
}

export const useProductStore = create<ProductStore>((set, get) => ({
  items: [],
  isLoading: false,
  error: null,

  async fetchAll(params) {
    set({ isLoading: true, error: null })
    try {
      const response = await api.fetchProducts(params)
      set({ items: response.data.data })
    } catch (e: any) {
      set({ error: e.message ?? 'Ошибка загрузки' })
    } finally {
      set({ isLoading: false })
    }
  },

  async create(data) {
    const response = await api.createProduct(data)
    const newItem = response.data.data
    set((state) => ({ items: [...state.items, newItem] }))
    return newItem
  },
}))
```

## Навигация

```typescript
// navigation/types.ts
export type RootStackParamList = {
  ProductList: undefined
  ProductDetail: { productId: number }
  ProductCreate: undefined
}

// navigation/RootNavigator.tsx
import { NavigationContainer } from '@react-navigation/native'
import { createNativeStackNavigator } from '@react-navigation/native-stack'
import type { RootStackParamList } from './types'

const Stack = createNativeStackNavigator<RootStackParamList>()

export function RootNavigator() {
  return (
    <NavigationContainer>
      <Stack.Navigator>
        <Stack.Screen name="ProductList" component={ProductListScreen} options={{ title: 'Продукты' }} />
        <Stack.Screen name="ProductDetail" component={ProductDetailScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  )
}
```

## Безопасное хранение токенов

```typescript
import * as SecureStore from 'expo-secure-store'

export const tokenStorage = {
  get: (key: string) => SecureStore.getItemAsync(key),
  set: (key: string, value: string) => SecureStore.setItemAsync(key, value),
  remove: (key: string) => SecureStore.deleteItemAsync(key),
}
```

## Чеклист перед сдачей

- [ ] Нет `any` в TypeScript без необходимости
- [ ] Только `StyleSheet.create()`, нет inline `style={{ ... }}`
- [ ] `SafeAreaView` на каждом корневом экране
- [ ] `KeyboardAvoidingView` на экранах с формами
- [ ] Токены в SecureStore, не в AsyncStorage
- [ ] `FlatList` вместо `ScrollView + map` для длинных списков
- [ ] Нет API-запросов напрямую в компонентах
- [ ] Нет забытых `console.log`
