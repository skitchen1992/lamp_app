import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 260_000


class InvalidAccessToken(Exception):
    pass


class ExpiredAccessToken(Exception):
    pass


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return "$".join(
        (
            PASSWORD_HASH_ALGORITHM,
            str(PASSWORD_HASH_ITERATIONS),
            _base64_url_encode(salt),
            _base64_url_encode(digest),
        )
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, encoded_salt, encoded_digest = password_hash.split("$")
    except ValueError:
        return False

    if algorithm != PASSWORD_HASH_ALGORITHM:
        return False

    salt = _base64_url_decode(encoded_salt)
    expected_digest = _base64_url_decode(encoded_digest)
    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        int(iterations),
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    user_id: UUID,
    secret: str,
    ttl_seconds: int,
    *,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=ttl_seconds)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    signing_input = ".".join(
        (
            _base64_url_encode_json(header),
            _base64_url_encode_json(payload),
        )
    )
    signature = _sign(signing_input, secret)
    return f"{signing_input}.{signature}"


def read_access_token(
    token: str,
    secret: str,
    *,
    now: datetime | None = None,
) -> UUID:
    try:
        encoded_header, encoded_payload, signature = token.split(".")
    except ValueError as exc:
        raise InvalidAccessToken from exc

    signing_input = f"{encoded_header}.{encoded_payload}"
    expected_signature = _sign(signing_input, secret)
    if not hmac.compare_digest(signature, expected_signature):
        raise InvalidAccessToken

    try:
        payload = json.loads(_base64_url_decode(encoded_payload))
        expires_at = datetime.fromtimestamp(int(payload["exp"]), timezone.utc)
        user_id = UUID(str(payload["sub"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise InvalidAccessToken from exc

    current_time = now or datetime.now(timezone.utc)
    if expires_at <= current_time:
        raise ExpiredAccessToken

    return user_id


def _sign(value: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _base64_url_encode(digest)


def _base64_url_encode_json(value: dict[str, object]) -> str:
    return _base64_url_encode(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )


def _base64_url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64_url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
