# Lamp App Microservices

Backend for the lamp factory shop. The repository contains four FastAPI
services:

- `api-gateway-service`
- `auth-service`
- `product-management-service`
- `order-management-service`

## Architecture

`api-gateway-service` is the only HTTP entrypoint. All client traffic and all
service-to-service HTTP calls must go through it.

```text
Client
  |
  v
api-gateway-service
  |-- /register, /login, /refresh, /logout, /me -> auth-service
  |-- /api/v1/products, /api/v1/categories -> product-management-service
  |-- /api/v1/cart, /api/v1/orders         -> order-management-service

order-management-service
  |
  v
api-gateway-service
  |
  v
product-management-service
```

In Docker Compose, only the API Gateway is published to the host. Domain
services are available only inside the compose network. For local Poetry
development, the domain services can still be started on separate ports, but
API calls should still target the gateway.

## Services

Each service has a health endpoint:

- `GET /health`

Domain service health endpoints check that the service is alive and can connect
to its own PostgreSQL database. The API Gateway health endpoint reports gateway
availability.

`auth-service` owns users and refresh sessions. The API Gateway routes these
endpoints to it:

- `POST /register`
- `POST /login`
- `POST /refresh`
- `POST /logout`
- `GET /me`

`product-management-service` owns product and category data. The API Gateway
routes these endpoints to it:

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

`order-management-service` owns carts and orders. The API Gateway routes these
endpoints to it:

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

Public endpoint:

- `http://127.0.0.1:8000/health`

Use `http://127.0.0.1:8000` for every API request. Product and order services
are intentionally not exposed on host ports by Docker Compose.

The API Gateway and databases are bound to `127.0.0.1` by default. Change
`SERVICE_BIND_ADDRESS`, `DATABASE_BIND_ADDRESS`, `GATEWAY_SERVICE_PORT`, and
the database `*_PORT` values in `.env` if your deployment target needs
different bindings.

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
docker compose up auth-db product-db order-db
```

Run a service:

```bash
poetry run uvicorn services.api_gateway_service.app.main:app --reload --port 8000
poetry run uvicorn services.product_management_service.app.main:app --reload --port 8001
poetry run uvicorn services.order_management_service.app.main:app --reload --port 8002
poetry run uvicorn services.auth_service.app.main:app --reload --port 8003
```

Keep all four processes running for order flows. The order service uses the
gateway for product lookups, so cart calculation and order creation need the
gateway and product service to be available.

## Environment configuration

Runtime database settings can be provided either as a full service-specific URL
or as split values:

- `AUTH_DATABASE_URL`, `PRODUCT_DATABASE_URL`, `ORDER_DATABASE_URL`
- `*_DATABASE_HOST`, `*_DATABASE_PORT`, `*_DATABASE_NAME`,
  `*_DATABASE_USER`, `*_DATABASE_PASSWORD`
- `AUTH_ACCESS_TOKEN_SECRET` for signing auth access tokens.
- `ORDER_PRODUCT_SERVICE_URL` for synchronous product lookups during cart
  calculation and order creation. It must point to the API Gateway.
- `GATEWAY_AUTH_SERVICE_URL`, `GATEWAY_PRODUCT_SERVICE_URL`, and
  `GATEWAY_ORDER_SERVICE_URL` for gateway upstream routing.

When a full URL is set, it takes priority. Otherwise, the app builds the URL
from the split values. Docker Compose uses split values for database names,
users, and passwords, then points application containers at the internal
database service names.

Default local ports:

- API Gateway: `8000`
- Product service: `8001`
- Order service: `8002`
- Auth service: `8003`
- Product database: `5433`
- Order database: `5434`
- Auth database: `5435`

## Checks

```bash
poetry run black --check .
poetry run pytest
```
