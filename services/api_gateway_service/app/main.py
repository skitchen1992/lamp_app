import asyncio
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException, Request, status
from starlette.responses import Response

from services.api_gateway_service.app.settings import Settings
from services.common.logging import setup_logging
from services.common.schemas import HealthResponse

APP_VERSION = "0.1.0"

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


@dataclass(frozen=True)
class Upstream:
    name: str
    base_url: str


settings = Settings()
app = FastAPI(title=settings.service_name, version=APP_VERSION)
setup_logging(app, settings.service_name)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        service=settings.service_name,
        status="ok",
        database="ok",
        version=APP_VERSION,
    )


@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def gateway_proxy(full_path: str, request: Request) -> Response:
    upstream = resolve_upstream(request.url.path)
    if upstream is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route is not registered in API Gateway",
        )

    body = await request.body()
    return await forward_request(request, upstream, body)


def resolve_upstream(path: str) -> Upstream | None:
    if path_matches(
        path,
        (
            "/register",
            "/login",
            "/refresh",
            "/logout",
            "/me",
        ),
    ):
        return Upstream("auth-service", settings.auth_service_url)

    if path_matches(
        path,
        (
            "/api/v1/products",
            "/api/v1/categories",
            "/api/v1/internal/products",
            "/api/v1/internal/categories",
        ),
    ):
        return Upstream("product-management-service", settings.product_service_url)

    if path_matches(
        path,
        (
            "/api/v1/cart",
            "/api/v1/orders",
            "/api/v1/internal/orders",
        ),
    ):
        return Upstream("order-management-service", settings.order_service_url)

    return None


def path_matches(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in prefixes)


async def forward_request(
    request: Request,
    upstream: Upstream,
    body: bytes,
) -> Response:
    return await asyncio.to_thread(_forward_request_sync, request, upstream, body)


def _forward_request_sync(
    request: Request,
    upstream: Upstream,
    body: bytes,
) -> Response:
    url = build_upstream_url(request, upstream)
    headers = build_forward_headers(request)
    data = body if body else None
    upstream_request = UrlRequest(
        url,
        data=data,
        headers=headers,
        method=request.method,
    )

    try:
        with urlopen(
            upstream_request,
            timeout=settings.upstream_timeout_seconds,
        ) as upstream_response:
            return response_from_upstream(
                upstream_response.status,
                upstream_response.headers.items(),
                upstream_response.read(),
            )
    except HTTPError as exc:
        return response_from_upstream(exc.code, exc.headers.items(), exc.read())
    except (OSError, TimeoutError, URLError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{upstream.name} is unavailable",
        ) from exc


def build_upstream_url(request: Request, upstream: Upstream) -> str:
    url = f"{upstream.base_url.rstrip('/')}{request.url.path}"
    if request.url.query:
        return f"{url}?{request.url.query}"
    return url


def build_forward_headers(request: Request) -> dict[str, str]:
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }
    if request.client:
        prior_forwarded_for = request.headers.get("x-forwarded-for")
        forwarded_for = request.client.host
        if prior_forwarded_for:
            forwarded_for = f"{prior_forwarded_for}, {forwarded_for}"
        headers["x-forwarded-for"] = forwarded_for
    if host := request.headers.get("host"):
        headers["x-forwarded-host"] = host
    headers["x-forwarded-proto"] = request.url.scheme
    return headers


def response_from_upstream(
    status_code: int,
    headers: list[tuple[str, str]],
    body: bytes,
) -> Response:
    response_headers = {
        key: value for key, value in headers if key.lower() not in HOP_BY_HOP_HEADERS
    }
    return Response(
        content=body,
        status_code=status_code,
        headers=response_headers,
    )
