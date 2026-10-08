"""
Protection against SSRF: a tenant must not be able to make the relay call internal services
(cloud metadata at 169.254.169.254, the database, localhost admin panels...).
"""

import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeUrl(ValueError):
    pass


def check_url(url: str, allow_private: bool) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise UnsafeUrl("URL must be http(s) with a host.")
    if allow_private:
        return
    if parts.scheme != "https":
        raise UnsafeUrl("URL must use https.")

    try:
        addresses = socket.getaddrinfo(parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as error:
        raise UnsafeUrl("Host does not resolve.") from error

    for *_, socket_address in addresses:
        if not ipaddress.ip_address(socket_address[0]).is_global:
            raise UnsafeUrl("URL resolves to a private or reserved address.")
