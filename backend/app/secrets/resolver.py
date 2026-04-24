"""Secret reference resolver.

Supported schemes:
  secret://paper/none       — paper adapter sentinel; resolves to empty string.
  secret://env/VAR_NAME     — reads os.environ[VAR_NAME] at call time.

Slice 4 will add file:// and vault:// backends.  The interface is
intentionally tiny: callers receive the plaintext value; they must not
log or serialise it.
"""
from __future__ import annotations

import os


def resolve(ref: str) -> str:
    """Resolve a secret:// reference to its plaintext value.

    Raises ValueError for unknown schemes or missing env vars.
    Never logs the resolved value.
    """
    if ref == "secret://paper/none":
        return ""

    if ref.startswith("secret://env/"):
        var = ref.removeprefix("secret://env/")
        value = os.environ.get(var)
        if value is None:
            raise ValueError(
                f"secret reference {ref!r} requires env var {var!r} which is not set"
            )
        return value

    raise ValueError(
        f"unsupported secret scheme in {ref!r}. "
        "Supported: secret://paper/none, secret://env/VAR_NAME"
    )
