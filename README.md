# Lamp App Microservices

First-stage backend build for the lamp factory shop. The repository contains
three separately runnable FastAPI services:

- `product-management-service`
- `order-management-service`
- `admin-panel-service`

Each service has a health endpoint:

- `GET /health`

The endpoint checks that the service is alive and can connect to its own
PostgreSQL database.

`product-management-service` implements the product API from the project
contract:

- `GET /api/v1/products`
- `GET /api/v1/products/{id}`
- `GET /api/v1/categories`
- `POST /api/v1/internal/categories`
- `PUT /api/v1/internal/categories/{id}`
- `DELETE /api/v1/internal/categories/{id}`
- `POST /api/v1/internal/products`
- `PUT /api/v1/internal/products/{id}`
- `PATCH /api/v1/internal/products/{id}/stock`
- `PATCH /api/v1/internal/products/{id}/status`
- `DELETE /api/v1/internal/products/{id}`

The product service initializes the product database schema on first use and
seeds the default lamp category used by the Postman examples.

`order-management-service` also implements the order API from the project
contract:

- `POST /api/v1/cart/calculate`
- `POST /api/v1/orders`
- `GET /api/v1/orders/{id}`
- `GET /api/v1/orders/{id}/status`
- `GET /api/v1/internal/orders`
- `PATCH /api/v1/internal/orders/{id}/status`

## Run with Docker Compose

Copy the environment template and replace every `change-me` password before
using it outside throwaway local development:

```bash
cp .env.example .env
```

```bash
docker compose up --build
```

Health endpoints:

- `http://127.0.0.1:8001/health`
- `http://127.0.0.1:8002/health`
- `http://127.0.0.1:8003/health`

Services and databases are bound to `127.0.0.1` by default. Change
`SERVICE_BIND_ADDRESS`, `DATABASE_BIND_ADDRESS`, and the `*_PORT` values in
`.env` if your deployment target needs different bindings.

## Run locally with Poetry

Install dependencies:

```bash
poetry install
```

Copy local database settings if you have not done it yet:

```bash
cp .env.example .env
```

Start databases:

```bash
docker compose up product-db order-db admin-db
```

Run a service:

```bash
poetry run uvicorn services.product_management_service.app.main:app --reload --port 8001
poetry run uvicorn services.order_management_service.app.main:app --reload --port 8002
poetry run uvicorn services.admin_panel_service.app.main:app --reload --port 8003
```

## Environment configuration

Runtime database settings can be provided either as a full service-specific URL
or as split values:

- `PRODUCT_DATABASE_URL`, `ORDER_DATABASE_URL`, `ADMIN_DATABASE_URL`
- `*_DATABASE_HOST`, `*_DATABASE_PORT`, `*_DATABASE_NAME`,
  `*_DATABASE_USER`, `*_DATABASE_PASSWORD`
- `ORDER_PRODUCT_SERVICE_URL` for synchronous product lookups during cart
  calculation and order creation.

When a full URL is set, it takes priority. Otherwise, the app builds the URL
from the split values. Docker Compose uses split values for database names,
users, and passwords, then points application containers at the internal
database service names.

## Checks

```bash
poetry run black --check .
poetry run pytest
```
