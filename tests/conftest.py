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
from fastapi.testclient import TestClient


@pytest.fixture
def client(banco):
    from app.main import criar_app

    with TestClient(criar_app(), follow_redirects=False) as c:
        yield c


import re

from app import seguranca

USUARIO = "admin"
SENHA = "senha-de-teste-123"  # valor descartável, só existe nos testes


@pytest.fixture
def senha():
    return SENHA


@pytest.fixture
def admin(banco):
    with db.transacao() as con:
        seguranca.criar_admin(con, USUARIO, SENHA)


@pytest.fixture
def logar(client, admin):
    def _logar(usuario=USUARIO, senha=SENHA):
        return client.post("/admin/login", data={"usuario": usuario, "senha": senha})

    return _logar


@pytest.fixture
def csrf_atual(client):
    def _csrf():
        return re.search(r'name="csrf" value="([^"]+)"', client.get("/admin").text).group(1)

    return _csrf
