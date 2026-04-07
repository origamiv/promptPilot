# Шаблон API-контракта (OpenAPI 3.0)

Файл сохраняется как `docs/api/openapi.yaml`

```yaml
openapi: 3.0.3
info:
  title: Project API
  version: 1.0.0
  description: REST API документация

servers:
  - url: /api/v1
    description: Production

components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

  schemas:
    # Стандартный ответ со списком
    PaginatedResponse:
      type: object
      properties:
        data:
          type: array
          items: {}
        meta:
          type: object
          properties:
            current_page: { type: integer }
            last_page:    { type: integer }
            per_page:     { type: integer }
            total:        { type: integer }

    # Стандартная ошибка валидации (422)
    ValidationError:
      type: object
      properties:
        message: { type: string, example: "The given data was invalid." }
        errors:
          type: object
          additionalProperties:
            type: array
            items: { type: string }

    # Стандартная ошибка (400/401/403/404/500)
    ErrorResponse:
      type: object
      properties:
        message: { type: string }

    # === Ресурс: Example ===
    ExampleResource:
      type: object
      properties:
        id:         { type: integer, example: 1 }
        name:       { type: string,  example: "Название" }
        status:     { type: string,  enum: [active, inactive] }
        created_at: { type: string,  format: date-time }
        updated_at: { type: string,  format: date-time }

security:
  - bearerAuth: []

paths:
  # === GET /examples — список ===
  /examples:
    get:
      summary: Список
      tags: [Examples]
      parameters:
        - in: query
          name: page
          schema: { type: integer, default: 1 }
        - in: query
          name: per_page
          schema: { type: integer, default: 15 }
        - in: query
          name: search
          schema: { type: string }
          description: Поиск по названию
      responses:
        '200':
          description: Список ресурсов
          content:
            application/json:
              schema:
                allOf:
                  - $ref: '#/components/schemas/PaginatedResponse'
                  - properties:
                      data:
                        items:
                          $ref: '#/components/schemas/ExampleResource'
        '401':
          description: Не авторизован
          content:
            application/json:
              schema: { $ref: '#/components/schemas/ErrorResponse' }

    # === POST /examples — создание ===
    post:
      summary: Создать
      tags: [Examples]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [name]
              properties:
                name:
                  type: string
                  minLength: 1
                  maxLength: 255
                status:
                  type: string
                  enum: [active, inactive]
                  default: active
      responses:
        '201':
          description: Создан
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { $ref: '#/components/schemas/ExampleResource' }
                  message: { type: string, example: "Создан успешно" }
        '422':
          description: Ошибка валидации
          content:
            application/json:
              schema: { $ref: '#/components/schemas/ValidationError' }

  # === GET/PUT/DELETE /examples/{id} ===
  /examples/{id}:
    parameters:
      - in: path
        name: id
        required: true
        schema: { type: integer }

    get:
      summary: Получить один
      tags: [Examples]
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { $ref: '#/components/schemas/ExampleResource' }
        '404':
          description: Не найден
          content:
            application/json:
              schema: { $ref: '#/components/schemas/ErrorResponse' }

    patch:
      summary: Обновить
      tags: [Examples]
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                name:   { type: string }
                status: { type: string, enum: [active, inactive] }
      responses:
        '200':
          description: Обновлён
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:    { $ref: '#/components/schemas/ExampleResource' }
                  message: { type: string }
        '404':
          description: Не найден
          content:
            application/json:
              schema: { $ref: '#/components/schemas/ErrorResponse' }
        '422':
          description: Ошибка валидации
          content:
            application/json:
              schema: { $ref: '#/components/schemas/ValidationError' }

    delete:
      summary: Удалить
      tags: [Examples]
      responses:
        '200':
          description: Удалён
          content:
            application/json:
              schema:
                type: object
                properties:
                  message: { type: string, example: "Удалён успешно" }
        '404':
          description: Не найден
          content:
            application/json:
              schema: { $ref: '#/components/schemas/ErrorResponse' }
```
