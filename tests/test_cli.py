import builtins
import getpass

import criar_admin
from app import db


def simular(monkeypatch, usuario, senha, repeticao):
    monkeypatch.setattr(builtins, "input", lambda _="": usuario)
    senhas = iter([senha, repeticao])
    monkeypatch.setattr(getpass, "getpass", lambda _="": next(senhas))


def test_cria_o_admin(banco, monkeypatch, capsys):
    simular(monkeypatch, "Admin", "senha-de-teste-123", "senha-de-teste-123")
    assert criar_admin.main() == 0
    with db.transacao() as con:
        assert db.obter_admin(con, "admin") is not None
    assert "senha-de-teste-123" not in capsys.readouterr().out


def test_senhas_diferentes_nao_criam(banco, monkeypatch):
    simular(monkeypatch, "admin", "senha-de-teste-123", "outra-senha-longa-1")
    assert criar_admin.main() == 1
    with db.transacao() as con:
        assert db.obter_admin(con, "admin") is None


def test_senha_curta_e_recusada(banco, monkeypatch, capsys):
    simular(monkeypatch, "admin", "curta", "curta")
    assert criar_admin.main() == 1
    assert "12" in capsys.readouterr().out


def test_usuario_repetido_e_recusado(banco, monkeypatch, capsys):
    simular(monkeypatch, "admin", "senha-de-teste-123", "senha-de-teste-123")
    assert criar_admin.main() == 0
    simular(monkeypatch, "admin", "senha-de-teste-123", "senha-de-teste-123")
    assert criar_admin.main() == 1
    assert "já existe" in capsys.readouterr().out
