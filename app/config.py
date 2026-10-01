import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def database_path() -> Path:
    return Path(os.environ.get("DATABASE_PATH", RAIZ / "inscricoes.db"))


def cookie_secure() -> bool:
    # Decisão 5: Secure só funciona em HTTPS; em http://localhost fica desligado.
    return os.environ.get("COOKIE_SECURE", "0") == "1"
