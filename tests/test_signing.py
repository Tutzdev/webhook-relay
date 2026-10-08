import time

from webhooks.models import new_signing_secret
from webhooks.services.signing import sign, signature_header, verify

BODY = b'{"type":"deposit.posted"}'


def headers_for(secret_list, timestamp, body=BODY):
    return {
        "webhook-id": "msg_1",
        "webhook-timestamp": str(timestamp),
        "webhook-signature": signature_header(secret_list, "msg_1", timestamp, body),
    }


def test_a_receiver_verifies_a_signed_request():
    secret = new_signing_secret()
    now = int(time.time())

    assert verify(secret, headers_for([secret], now), BODY, now)


def test_a_tampered_body_fails_verification():
    secret = new_signing_secret()
    now = int(time.time())

    assert not verify(secret, headers_for([secret], now), b'{"type":"withdrawal.posted"}', now)


def test_an_old_request_is_rejected_even_with_a_valid_signature():
    secret = new_signing_secret()
    ten_minutes_ago = int(time.time()) - 600

    assert not verify(secret, headers_for([secret], ten_minutes_ago), BODY, int(time.time()))


def test_both_secrets_sign_during_a_rotation():
    old_secret, new_secret = new_signing_secret(), new_signing_secret()
    now = int(time.time())
    headers = headers_for([new_secret, old_secret], now)

    assert verify(old_secret, headers, BODY, now)
    assert verify(new_secret, headers, BODY, now)
    assert headers["webhook-signature"].split()[0] == sign(new_secret, "msg_1", now, BODY)
