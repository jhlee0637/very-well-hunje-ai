"""TLS defaults shared by outbound Lunit clients."""

from __future__ import annotations

import ssl


def create_tls_context() -> ssl.SSLContext:
    """Create a verified context compatible with local TLS inspection CAs.

    Python 3.13 enables OpenSSL's strict X.509 mode by default. Some managed
    network products install an otherwise trusted root CA whose Basic
    Constraints extension is not marked critical. Clearing only the strict
    flag preserves certificate-chain and hostname verification while allowing
    those locally trusted roots.
    """

    context = ssl.create_default_context()
    strict_flag = getattr(ssl, "VERIFY_X509_STRICT", 0)
    if strict_flag:
        context.verify_flags &= ~strict_flag
    return context