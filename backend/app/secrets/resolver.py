"""Secret reference resolver.

Supported schemes:
  secret://paper/none       — paper adapter sentinel; resolves to empty string.
  secret://env/VAR_NAME     — reads os.environ[VAR_NAME] at call time.
  secret://file/path/to/file — reads first line of file, stripped.

Vault / AWS Secrets Manager backends raise NotImplementedError (interface
reserved for a future slice).  Callers receive the plaintext value; they
must not log or serialise it.
"""
from __future__ import annotations

import os
from pathlib import Path


def resolve(ref: str) -> str:
    """Resolve a secret:// reference to its plaintext value.

    Raises ValueError for unknown schemes, missing env vars, or unreadable
    files.  Never logs the resolved value.
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

    if ref.startswith("secret://file/"):
        path_str = ref.removeprefix("secret://file/")
        path = Path(path_str)
        if not path.exists():
            raise ValueError(f"secret file {path_str!r} does not exist (from {ref!r})")
        content = path.read_text(encoding="utf-8").splitlines()
        if not content or not content[0].strip():
            raise ValueError(f"secret file {path_str!r} is empty (from {ref!r})")
        return content[0].strip()

    if ref.startswith("secret://vault/") or ref.startswith("secret://aws/"):
        raise NotImplementedError(
            f"secret backend for {ref!r} is not yet implemented. "
            "Use secret://env/ or secret://file/ instead."
        )

    raise ValueError(
        f"unsupported secret scheme in {ref!r}. "
        "Supported: secret://paper/none, secret://env/VAR_NAME, secret://file/path"
    )
