import pytest

from app import db


@pytest.fixture
def banco(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "teste.db"))
    db.iniciar()


@pytest.fixture
def con(banco):
    with db.transacao() as c:
        yield c
