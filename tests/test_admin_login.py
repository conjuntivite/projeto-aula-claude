import hashlib
import re

import pytest

from app import db, seguranca


def sessoes():
    with db.transacao() as con:
        return [dict(r) for r in con.execute("SELECT * FROM sessoes")]


def token_do_cookie(resposta):
    return re.match(r"sessao=([^;]+)", resposta.headers["set-cookie"]).group(1)


def flags(resposta):
    return [p.strip().lower() for p in resposta.headers["set-cookie"].split(";")[1:]]


def test_login_correto_redireciona_e_cookie_e_restrito(client, logar):
    r = logar()
    assert r.status_code == 303 and r.headers["location"] == "/admin"
    f = flags(r)
    assert "httponly" in f and "samesite=strict" in f and "path=/admin" in f and "secure" not in f


def test_cookie_secure_vem_da_configuracao(client, logar, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "1")
    assert "secure" in flags(logar())


def test_banco_guarda_so_o_hash_do_token(client, logar):
    token = token_do_cookie(logar())
    [s] = sessoes()
    assert s["token_hash"] != token and s["token_hash"] == hashlib.sha256(token.encode()).hexdigest()


def test_pagina_do_admin_autenticada(client, logar):
    logar()
    r = client.get("/admin")
    assert r.status_code == 200 and "admin" in r.text and r.headers["cache-control"] == "no-store"


def test_sem_sessao_redireciona_para_o_login(client, admin):
    r = client.get("/admin")
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"


@pytest.mark.parametrize("cookie", ["sessao=", "sessao=" + "x" * 5000, "sessao=çã", "sessao=" + "A" * 43])
def test_cookie_adulterado_nao_autentica_nem_quebra(client, admin, cookie):
    r = client.get("/admin", headers={"Cookie": cookie.encode()})  # bytes: o httpx recusa str não-ASCII em cabeçalho
    assert r.status_code == 303


def test_usuario_inexistente_e_senha_errada_respondem_igual(client, logar):
    a = logar(usuario="admin", senha="senha-errada-123")
    b = logar(usuario="fantasma", senha="senha-errada-123")
    assert a.status_code == b.status_code == 401
    assert a.text == b.text and "inválidos" in a.text


def test_usuario_inexistente_tambem_gasta_um_hash(client, logar, monkeypatch):
    chamadas = []
    original = seguranca.verificar_senha
    monkeypatch.setattr(seguranca, "verificar_senha", lambda h, s: chamadas.append(h) or original(h, s))
    logar(usuario="fantasma", senha="senha-errada-123")
    assert chamadas == [seguranca.HASH_FALSO]


def test_bloqueia_apos_cinco_falhas_mesmo_com_a_senha_certa(client, logar):
    for _ in range(5):
        assert logar(senha="senha-errada-123").status_code == 401
    assert logar().status_code == 429
    assert client.get("/admin").status_code == 303


def test_bloqueio_vale_tambem_para_usuario_inexistente(client, logar):
    for _ in range(5):
        logar(usuario="fantasma", senha="x-senha-qualquer")
    assert logar(usuario="fantasma", senha="x-senha-qualquer").status_code == 429


def test_cada_login_cria_token_novo(client, logar):
    t1 = token_do_cookie(logar())
    t2 = token_do_cookie(logar())
    assert t1 != t2


def test_login_com_sessao_antiga_apaga_a_antiga(client, logar):
    logar()
    logar()
    assert len(sessoes()) == 1


@pytest.mark.parametrize("senha,esperado", [("ç" * 1024, 401), ("a" * 1025, 422), ("", 422)])
def test_senha_hostil_nao_gera_500(client, logar, senha, esperado):
    assert logar(senha=senha).status_code == esperado


def test_usuario_vazio_ou_gigante_nao_gera_500(client, logar):
    assert logar(usuario="").status_code == 422
    assert logar(usuario="u" * 101).status_code == 422


def test_logout_com_csrf_invalida_a_sessao(client, logar, csrf_atual):
    logar()
    r = client.post("/admin/logout", data={"csrf": csrf_atual()})
    assert r.status_code == 303 and r.headers["location"] == "/admin/login"
    assert sessoes() == []
    assert client.get("/admin").status_code == 303


@pytest.mark.parametrize("csrf", [None, "", "errado", "çãé"])
def test_logout_sem_csrf_valido_e_recusado(client, logar, csrf):
    logar()
    dados = {} if csrf is None else {"csrf": csrf}
    assert client.post("/admin/logout", data=dados).status_code == 403
    assert len(sessoes()) == 1


def test_sessao_expirada_e_recusada(client, logar):
    logar()
    with db.transacao() as con:
        con.execute("UPDATE sessoes SET expira_em = ?", (db.agora_mais(-5),))
    assert client.get("/admin").status_code == 303


def test_toda_rota_do_admin_exceto_o_login_exige_sessao(client, admin):
    verificadas = 0
    for rota in client.app.routes:
        caminho = getattr(rota, "path", "")
        if not caminho.startswith("/admin") or caminho == "/admin/login":
            continue
        for metodo in rota.methods - {"HEAD", "OPTIONS"}:
            r = client.request(metodo, re.sub(r"\{[^}]+\}", "1", caminho))
            assert r.status_code in (303, 401), (metodo, caminho, r.status_code)
            verificadas += 1
    assert verificadas >= 2


def test_senha_nao_aparece_no_banco_nem_nos_logs(client, logar, senha, caplog, tmp_path):
    caplog.set_level("DEBUG")
    logar()
    assert senha not in caplog.text
    assert senha.encode() not in (tmp_path / "teste.db").read_bytes()
