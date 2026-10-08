"""
Signatures follow the Standard Webhooks spec (https://www.standardwebhooks.com), the same scheme
used by several public webhook providers, so receivers can verify with an off-the-shelf library.
"""

import base64
import hashlib
import hmac
from collections.abc import Iterable, Mapping

from webhooks.models import SECRET_PREFIX

SIGNATURE_VERSION = "v1"
DEFAULT_TOLERANCE_SECONDS = 5 * 60


def sign(secret: str, message_id: str, timestamp: int, body: bytes) -> str:
    key = base64.b64decode(secret.removeprefix(SECRET_PREFIX))
    signed_content = f"{message_id}.{timestamp}.".encode() + body
    digest = hmac.new(key, signed_content, hashlib.sha256).digest()
    return f"{SIGNATURE_VERSION},{base64.b64encode(digest).decode()}"


def signature_header(secrets: Iterable[str], message_id: str, timestamp: int, body: bytes) -> str:
    return " ".join(sign(secret, message_id, timestamp, body) for secret in secrets)


def verify(
    secret: str,
    headers: Mapping[str, str],
    body: bytes,
    now: int,
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
) -> bool:
    """What a receiver runs. The timestamp check stops an attacker from replaying an old, valid request."""
    try:
        message_id = headers["webhook-id"]
        timestamp = int(headers["webhook-timestamp"])
        signatures = headers["webhook-signature"].split()
    except (KeyError, ValueError):
        return False

    if abs(now - timestamp) > tolerance_seconds:
        return False
    expected = sign(secret, message_id, timestamp, body)
    return any(hmac.compare_digest(expected, candidate) for candidate in signatures)
