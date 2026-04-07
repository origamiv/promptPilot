# Конвенции: Vue.js 2

## Структура директорий

```
resources/js/
├── api/                  # HTTP-клиент и функции запросов
│   ├── client.js         # Axios instance
│   └── products.js
├── components/           # Переиспользуемые компоненты
│   ├── ui/
│   ├── forms/
│   └── layout/
├── pages/                # Страницы / роуты
├── router/               # Vue Router 3
│   └── index.js
├── store/                # Vuex store
│   ├── index.js
│   └── modules/
│       └── products.js
└── app.js                # Точка входа
```

## Именование

| Тип | Конвенция | Пример |
|-----|-----------|--------|
| Компонент | PascalCase | `ProductCard.vue` |
| Страница | PascalCase + Page | `ProductListPage.vue` |
| Vuex модуль | camelCase | `products`, `auth` |
| API-функция | глагол + ресурс | `fetchProducts`, `createProduct` |

## Структура компонента (Options API)

```vue
<script>
import { mapState, mapActions } from 'vuex'
import { fetchProduct } from '@/api/products'

export default {
  name: 'ProductForm',

  components: { /* ... */ },

  props: {
    productId: {
      type: Number,
      required: true,
    },
  },

  data() {
    return {
      isLoading: false,
      error: null,
      form: {
        name: '',
        price: null,
      },
    }
  },

  computed: {
    ...mapState('products', ['items']),
    hasChanges() {
      return this.form.name !== ''
    },
  },

  watch: {
    productId(newId) {
      this.loadProduct(newId)
    },
  },

  created() {
    this.loadProduct(this.productId)
  },

  methods: {
    ...mapActions('products', ['updateProduct']),

    async loadProduct(id) {
      this.isLoading = true
      this.error = null
      try {
        const { data } = await fetchProduct(id)
        this.form = { ...data.data }
      } catch (e) {
        this.error = 'Не удалось загрузить'
      } finally {
        this.isLoading = false
      }
    },

    async handleSubmit() {
      this.isLoading = true
      try {
        await this.updateProduct({ id: this.productId, ...this.form })
        this.$emit('saved')
      } catch (e) {
        this.error = 'Не удалось сохранить'
      } finally {
        this.isLoading = false
      }
    },
  },
}
</script>

<template>
  <div>
    <div v-if="isLoading">Загрузка...</div>
    <div v-else-if="error">{{ error }}</div>
    <form v-else @submit.prevent="handleSubmit">
      <!-- поля формы -->
    </form>
  </div>
</template>
```

## Vuex модуль

```javascript
// store/modules/products.js
import * as api from '@/api/products'

export default {
  namespaced: true,

  state: () => ({
    items: [],
    isLoading: false,
    error: null,
  }),

  getters: {
    getById: (state) => (id) => state.items.find(item => item.id === id),
  },

  mutations: {
    SET_ITEMS(state, items) { state.items = items },
    SET_LOADING(state, val) { state.isLoading = val },
    SET_ERROR(state, err) { state.error = err },
    ADD_ITEM(state, item) { state.items.push(item) },
    UPDATE_ITEM(state, updated) {
      const idx = state.items.findIndex(i => i.id === updated.id)
      if (idx !== -1) state.items.splice(idx, 1, updated)
    },
  },

  actions: {
    async fetchAll({ commit }, params) {
      commit('SET_LOADING', true)
      commit('SET_ERROR', null)
      try {
        const { data } = await api.fetchProducts(params)
        commit('SET_ITEMS', data.data)
      } catch (e) {
        commit('SET_ERROR', 'Не удалось загрузить')
        throw e
      } finally {
        commit('SET_LOADING', false)
      }
    },
  },
}
```

## Чеклист перед сдачей

- [ ] Порядок секций в компоненте: `name → components → props → data → computed → watch → lifecycle → methods`
- [ ] Нет прямых axios-вызовов в компонентах — только через Vuex actions или API-слой
- [ ] Все мутации через commit, не прямое изменение state
- [ ] Все асинхронные операции имеют loading/error состояния
- [ ] Формы блокируются во время отправки
- [ ] Нет забытых `console.log`
