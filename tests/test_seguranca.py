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


@pytest.mark.parametrize("senha", ["\ud800", None])
def test_verificar_com_senha_hostil_devolve_false(senha):
    assert seguranca.verificar_senha(seguranca.HASH_FALSO, senha) is False
    assert seguranca.verificar_senha(seguranca.hash_senha(SENHA), senha) is False


@pytest.mark.parametrize("hash_", ["\ud800", None])
def test_verificar_com_hash_hostil_devolve_false(hash_):
    assert seguranca.verificar_senha(hash_, SENHA) is False


def test_bloqueia_na_quinta_falha_do_mesmo_usuario_e_ip(con):
    for _ in range(4):
        seguranca.registrar_falha(con, "admin", "1.1.1.1")
    assert seguranca.bloqueado(con, "admin", "1.1.1.1") is False
    seguranca.registrar_falha(con, "admin", "1.1.1.1")
    assert seguranca.bloqueado(con, "admin", "1.1.1.1") is True


def test_outro_ip_ou_outro_usuario_nao_e_bloqueado(con):
    for _ in range(5):
        seguranca.registrar_falha(con, "admin", "1.1.1.1")
    assert seguranca.bloqueado(con, "admin", "2.2.2.2") is False
    assert seguranca.bloqueado(con, "outro", "1.1.1.1") is False


def test_usuario_ignora_maiusculas_e_espacos(con):
    for _ in range(5):
        seguranca.registrar_falha(con, " Admin ", "1.1.1.1")
    assert seguranca.bloqueado(con, "admin", "1.1.1.1") is True


def test_falhas_antigas_nao_contam(con):
    for _ in range(5):
        con.execute("INSERT INTO tentativas_login (usuario, ip, criada_em) VALUES (?, ?, ?)",
                    ("admin", "1.1.1.1", db.agora_mais(-(seguranca.JANELA_LOGIN_S + 1))))
    assert seguranca.bloqueado(con, "admin", "1.1.1.1") is False


def test_limpar_falhas_zera_o_contador(con):
    for _ in range(5):
        seguranca.registrar_falha(con, "admin", "1.1.1.1")
    seguranca.limpar_falhas(con, "admin", "1.1.1.1")
    assert seguranca.bloqueado(con, "admin", "1.1.1.1") is False


def test_limpar_expiradas_apaga_tentativas_antigas(con):
    con.execute("INSERT INTO tentativas_login (usuario, ip, criada_em) VALUES (?, ?, ?)",
                ("admin", "1.1.1.1", db.agora_mais(-(seguranca.JANELA_LOGIN_S + 1))))
    seguranca.registrar_falha(con, "admin", "1.1.1.1")
    seguranca.limpar_expiradas(con)
    assert con.execute("SELECT COUNT(*) FROM tentativas_login").fetchone()[0] == 1


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_limitador_bloqueia_apos_o_maximo_e_libera_depois_da_janela():
    r = Relogio()
    lim = seguranca.LimitadorPorIp(maximo=3, janela_s=60, relogio=r)
    assert [lim.permitir("1.1.1.1") for _ in range(4)] == [True, True, True, False]
    assert lim.permitir("2.2.2.2") is True
    r.t += 61
    assert lim.permitir("1.1.1.1") is True
