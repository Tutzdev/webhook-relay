import socket

import pytest

from webhooks.services.url_guard import UnsafeUrl, check_url


def resolving_to(ip):
    return lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.20", "169.254.169.254", "172.17.0.1"])
def test_blocks_urls_that_resolve_to_internal_addresses(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", resolving_to(ip))

    with pytest.raises(UnsafeUrl):
        check_url("https://hooks.example.com/ledger", allow_private=False)


def test_accepts_a_public_https_url(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", resolving_to("93.184.216.34"))

    check_url("https://hooks.example.com/ledger", allow_private=False)


def test_requires_https_in_production():
    with pytest.raises(UnsafeUrl):
        check_url("http://hooks.example.com/ledger", allow_private=False)
