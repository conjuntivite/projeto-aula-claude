import sqlite3

import pytest

from app import config, db


def dados(email="teste1@exemplo.com", curso="Direito", nome="Aluno Teste"):
    return {
        "nome": nome, "email": email, "email_normalizado": email.strip().lower(),
        "curso": curso, "periodo": 3, "experiencia": "basica",
        "consentimento_em": "2026-10-01T12:00:00+00:00", "versao_consentimento": "2026-10-01",
    }


def test_config_le_variaveis_de_ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "x.db"))
    monkeypatch.setenv("COOKIE_SECURE", "1")
    assert config.database_path() == tmp_path / "x.db"
    assert config.cookie_secure() is True


def test_cookie_secure_vem_desligado(monkeypatch):
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    assert config.cookie_secure() is False


def test_iniciar_cria_as_quatro_tabelas(con):
    nomes = {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"inscricoes", "admins", "sessoes", "tentativas_login"} <= nomes


def test_chaves_estrangeiras_ligadas(con):
    assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_inserir_grava_e_lista(con):
    assert db.inserir_inscricao(con, dados()) is True
    [linha] = db.listar_inscricoes(con)
    assert linha["nome"] == "Aluno Teste" and linha["periodo"] == 3 and linha["criado_em"]


def test_email_repetido_com_outra_grafia_nao_duplica(con):
    assert db.inserir_inscricao(con, dados("teste1@exemplo.com")) is True
    assert db.inserir_inscricao(con, dados("  TESTE1@Exemplo.com ")) is False
    assert db.contar(con) == 1


def test_banco_recusa_periodo_fora_do_intervalo(con):
    d = dados()
    d["periodo"] = 11
    with pytest.raises(sqlite3.IntegrityError):
        db.inserir_inscricao(con, d)


def test_listar_filtra_por_curso(con):
    db.inserir_inscricao(con, dados("a1@exemplo.com", "Direito"))
    db.inserir_inscricao(con, dados("a2@exemplo.com", "Design"))
    assert len(db.listar_inscricoes(con)) == 2
    assert [r["curso"] for r in db.listar_inscricoes(con, "Design")] == ["Design"]


def test_remover_inscricao(con):
    db.inserir_inscricao(con, dados())
    [linha] = db.listar_inscricoes(con)
    assert db.remover_inscricao(con, linha["id"]) is True
    assert db.remover_inscricao(con, linha["id"]) is False
    assert db.contar(con) == 0


def test_admin_criar_obter_e_usuario_repetido(con):
    admin_id = db.criar_admin_db(con, "admin", "hash-qualquer")
    assert db.obter_admin(con, "admin")["id"] == admin_id
    assert db.obter_admin(con, "ninguem") is None
    with pytest.raises(sqlite3.IntegrityError):
        db.criar_admin_db(con, "admin", "outro")


def test_atualizar_hash(con):
    admin_id = db.criar_admin_db(con, "admin", "velho")
    db.atualizar_hash(con, admin_id, "novo")
    assert db.obter_admin(con, "admin")["senha_hash"] == "novo"
