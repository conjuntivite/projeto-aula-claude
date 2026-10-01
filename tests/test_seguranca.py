import hashlib

import pytest

from app import db, seguranca

SENHA = "senha-de-teste-123"


def test_hash_nao_guarda_a_senha_e_verifica():
    h = seguranca.hash_senha(SENHA)
    assert h.startswith("$argon2id$") and SENHA not in h
    assert seguranca.verificar_senha(h, SENHA) is True
    assert seguranca.verificar_senha(h, "outra-senha-qualquer") is False


@pytest.mark.parametrize("lixo", ["", "lixo", "$argon2id$quebrado"])
def test_verificar_com_hash_invalido_devolve_false(lixo):
    assert seguranca.verificar_senha(lixo, SENHA) is False


def test_hash_falso_rejeita_qualquer_senha():
    assert seguranca.verificar_senha(seguranca.HASH_FALSO, SENHA) is False


def test_criar_admin_guarda_hash_e_usuario_em_minusculas(con):
    admin_id = seguranca.criar_admin(con, "  Admin ", SENHA)
    admin = db.obter_admin(con, "admin")
    assert admin["id"] == admin_id and admin["senha_hash"] != SENHA
    assert seguranca.verificar_senha(admin["senha_hash"], SENHA)


@pytest.mark.parametrize("usuario,senha", [("", SENHA), ("   ", SENHA), ("x" * 101, SENHA),
                                           ("admin", "curta-11-ch"), ("admin", "a" * 1025)])
def test_criar_admin_recusa_dados_invalidos(con, usuario, senha):
    with pytest.raises(ValueError):
        seguranca.criar_admin(con, usuario, senha)


def test_criar_admin_repetido(con):
    seguranca.criar_admin(con, "admin", SENHA)
    with pytest.raises(seguranca.UsuarioExistente):
        seguranca.criar_admin(con, "ADMIN", SENHA)


def test_sessao_guarda_so_o_hash_do_token(con):
    admin_id = seguranca.criar_admin(con, "admin", SENHA)
    token, csrf = seguranca.criar_sessao(con, admin_id)
    guardado = con.execute("SELECT token_hash FROM sessoes").fetchone()[0]
    assert guardado != token
    assert guardado == hashlib.sha256(token.encode()).hexdigest()
    sessao = seguranca.obter_sessao(con, token)
    assert sessao["usuario"] == "admin" and sessao["csrf_token"] == csrf and sessao["admin_id"] == admin_id


def test_cada_login_gera_token_novo(con):
    admin_id = seguranca.criar_admin(con, "admin", SENHA)
    t1, _ = seguranca.criar_sessao(con, admin_id)
    t2, _ = seguranca.criar_sessao(con, admin_id)
    assert t1 != t2


def test_sessao_expirada_e_recusada(con):
    admin_id = seguranca.criar_admin(con, "admin", SENHA)
    token, _ = seguranca.criar_sessao(con, admin_id)
    con.execute("UPDATE sessoes SET expira_em = ?", (db.agora_mais(-1),))
    assert seguranca.obter_sessao(con, token) is None


@pytest.mark.parametrize("token", [None, "", "x" * 5000, "çã", "token-que-nao-existe"])
def test_token_hostil_nao_autentica_nem_quebra(con, token):
    seguranca.criar_admin(con, "admin", SENHA)
    assert seguranca.obter_sessao(con, token) is None


def test_apagar_sessao_invalida_o_token(con):
    admin_id = seguranca.criar_admin(con, "admin", SENHA)
    token, _ = seguranca.criar_sessao(con, admin_id)
    seguranca.apagar_sessao(con, token)
    assert seguranca.obter_sessao(con, token) is None


def test_limpar_expiradas_remove_so_as_vencidas(con):
    admin_id = seguranca.criar_admin(con, "admin", SENHA)
    seguranca.criar_sessao(con, admin_id)
    seguranca.criar_sessao(con, admin_id)
    con.execute("UPDATE sessoes SET expira_em = ? WHERE rowid = 1", (db.agora_mais(-1),))
    seguranca.limpar_expiradas(con)
    assert con.execute("SELECT COUNT(*) FROM sessoes").fetchone()[0] == 1


def test_apagar_admin_apaga_as_sessoes(con):
    admin_id = seguranca.criar_admin(con, "admin", SENHA)
    seguranca.criar_sessao(con, admin_id)
    con.execute("DELETE FROM admins WHERE id = ?", (admin_id,))
    assert con.execute("SELECT COUNT(*) FROM sessoes").fetchone()[0] == 0


def test_csrf_valido():
    assert seguranca.csrf_valido("abc", "abc") is True
    assert seguranca.csrf_valido("abc", "abd") is False
    assert seguranca.csrf_valido("abc", "") is False
    assert seguranca.csrf_valido("abc", None) is False


def test_csrf_nao_ascii_nao_quebra():
    assert seguranca.csrf_valido("abc", "çãé") is False
    assert seguranca.csrf_valido("çãé", "çãé") is True
