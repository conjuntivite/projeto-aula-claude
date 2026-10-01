import pytest

from app import db
from app.validacao import MENSAGENS_ERRO


def payload(**o):
    d = {"nome": "Aluno Teste", "email": "teste1@exemplo.com", "curso": "Direito",
         "periodo": 3, "experiencia": "basica", "consentimento": True}
    d.update(o)
    return d


def linhas():
    with db.transacao() as con:
        return [dict(r) for r in db.listar_inscricoes(con)]


def test_inscricao_valida_grava_com_consentimento(client):
    r = client.post("/api/inscricoes", json=payload())
    assert r.status_code == 201 and "mensagem" in r.json()
    [i] = linhas()
    assert i["nome"] == "Aluno Teste" and i["consentimento_em"] and i["versao_consentimento"]


def test_duplicado_responde_igual_e_nao_grava_de_novo(client):
    novo = client.post("/api/inscricoes", json=payload())
    for email in ["teste1@exemplo.com", "  TESTE1@Exemplo.com ", "Teste1@EXEMPLO.COM"]:
        repetido = client.post("/api/inscricoes", json=payload(email=email, nome="Outro Nome"))
        assert repetido.status_code == novo.status_code == 201
        assert repetido.json() == novo.json()
    assert len(linhas()) == 1


def test_422_devolve_erros_por_campo_em_ptbr(client):
    r = client.post("/api/inscricoes", json=payload(nome="ab", periodo=11))
    assert r.status_code == 422
    erros = r.json()["erros"]
    assert erros["nome"] == MENSAGENS_ERRO["nome"] and erros["periodo"] == MENSAGENS_ERRO["periodo"]
    assert linhas() == []


def test_422_nao_ecoa_o_que_foi_enviado(client):
    r = client.post("/api/inscricoes", json=payload(nome="ab", email="<script>alert(1)</script>"))
    assert r.status_code == 422
    assert "<script>" not in r.text and "alert" not in r.text


@pytest.mark.parametrize("corpo", [b"{", b"", b"null", b"[]", b'"texto"', b"123", b'{"nome": 1}'])
def test_corpo_ilegivel_devolve_422_e_nao_500(client, corpo):
    r = client.post("/api/inscricoes", content=corpo, headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and "erros" in r.json()
    assert linhas() == []


@pytest.mark.parametrize("troca", [
    {"periodo": "3"}, {"periodo": None}, {"periodo": [3]}, {"periodo": True}, {"periodo": 3.5},
    {"email": ["a@b.co"]}, {"nome": {"x": 1}}, {"consentimento": "true"}, {"consentimento": False},
    {"experiencia": "toString"}, {"experiencia": ["basica"]}, {"extra": 1},
])
def test_tipos_errados_devolvem_422(client, troca):
    assert client.post("/api/inscricoes", json=payload(**troca)).status_code == 422
    assert linhas() == []


def test_sql_injection_vira_texto_literal(client):
    nome = "Robert'); DROP TABLE inscricoes;--"
    assert client.post("/api/inscricoes", json=payload(nome=nome)).status_code == 201
    assert [i["nome"] for i in linhas()] == [nome]


def test_limite_de_envios_por_ip(client):
    for n in range(10):
        assert client.post("/api/inscricoes", json=payload(email=f"a{n}@exemplo.com")).status_code == 201
    assert client.post("/api/inscricoes", json=payload(email="a10@exemplo.com")).status_code == 429
    assert len(linhas()) == 10


def test_cabecalhos_de_seguranca(client):
    for r in (client.get("/"), client.post("/api/inscricoes", json=payload())):
        csp = r.headers["content-security-policy"]
        assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "form-action 'self'" in csp
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "no-referrer"
    assert client.post("/api/inscricoes", json=payload()).headers["cache-control"] == "no-store"


@pytest.mark.parametrize("caminho", ["/docs", "/redoc", "/openapi.json"])
def test_documentacao_da_api_desligada(client, caminho):
    assert client.get(caminho).status_code == 404


@pytest.mark.parametrize("caminho", ["/inscricoes.db", "/app/main.py", "/%2e%2e/app/main.py", "/criar_admin.py"])
def test_so_a_pasta_publica_e_servida(client, caminho):
    assert client.get(caminho).status_code == 404


def test_pagina_publica_e_servida(client):
    r = client.get("/")
    assert r.status_code == 200 and "Claude AI" in r.text
