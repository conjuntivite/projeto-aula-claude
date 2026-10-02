import re

import pytest

from app import db


def semear(*itens):
    with db.transacao() as con:
        for nome, email, curso in itens:
            db.inserir_inscricao(con, {
                "nome": nome, "email": email, "email_normalizado": email.lower(), "curso": curso,
                "periodo": 2, "experiencia": "nenhuma",
                "consentimento_em": db.agora(), "versao_consentimento": "2026-10-01"})


def ids():
    with db.transacao() as con:
        return [r["id"] for r in db.listar_inscricoes(con)]


@pytest.fixture
def logado(client, logar):
    logar()
    return client


def test_lista_mostra_total_e_linhas(logado):
    semear(("Aluno Um", "a1@exemplo.com", "Direito"), ("Aluno Dois", "a2@exemplo.com", "Design"))
    html = logado.get("/admin").text
    assert "Total: 2 inscritos" in html and "Aluno Um" in html and "Aluno Dois" in html


def test_total_no_singular_e_estado_vazio(logado):
    assert "Nenhuma inscrição ainda" in logado.get("/admin").text
    semear(("Aluno Um", "a1@exemplo.com", "Direito"))
    assert "Total: 1 inscrito" in logado.get("/admin").text


def test_filtro_por_curso(logado):
    semear(("Aluno Um", "a1@exemplo.com", "Direito"), ("Aluno Dois", "a2@exemplo.com", "Design"),
           ("Aluno Tres", "a3@exemplo.com", "Direito"))
    html = logado.get("/admin", params={"curso": "Direito"}).text
    assert "Mostrando 2 de 3 inscritos (Direito)" in html and "Aluno Dois" not in html
    assert "Nenhum inscrito neste curso" in logado.get("/admin", params={"curso": "Medicina"}).text


@pytest.mark.parametrize("curso", ["Invalido", "' OR 1=1 --", "<script>", "", "%00", "x" * 5000])
def test_filtro_hostil_e_ignorado(logado, curso):
    semear(("Aluno Um", "a1@exemplo.com", "Direito"))
    r = logado.get("/admin", params={"curso": curso})
    assert r.status_code == 200 and "Total: 1 inscrito" in r.text


def test_filtro_repetido_nao_quebra(logado):
    assert logado.get("/admin?curso=Direito&curso=Design").status_code == 200


def test_nome_com_html_aparece_escapado(logado):
    semear(("<script>alert(1)</script>", "x1@exemplo.com", "Direito"),
           ('"><img src=x onerror=alert(1)>', "x2@exemplo.com", "Design"))
    html = logado.get("/admin").text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert '"><img' not in html


def test_html_sem_script_nem_evento_inline(logado):
    semear(("Aluno Um", "a1@exemplo.com", "Direito"))
    html = logado.get("/admin").text
    assert "onclick" not in html and "style=" not in html
    assert re.findall(r"<script(?![^>]*\bsrc=)", html) == []


def test_formulario_de_remocao_tem_confirmacao_e_csrf(logado):
    semear(("Aluno Um", "a1@exemplo.com", "Direito"))
    html = logado.get("/admin").text
    assert "data-confirmar=" in html and 'name="csrf"' in html


def test_remover_com_csrf(logado, csrf_atual):
    semear(("Aluno Um", "a1@exemplo.com", "Direito"), ("Aluno Dois", "a2@exemplo.com", "Design"))
    primeiro = ids()[0]
    r = logado.post(f"/admin/inscricoes/{primeiro}/remover", data={"csrf": csrf_atual()})
    assert r.status_code == 303 and r.headers["location"] == "/admin"
    assert primeiro not in ids() and len(ids()) == 1


@pytest.mark.parametrize("csrf", [None, "", "errado", "çãé"])
def test_remover_sem_csrf_valido_e_recusado(logado, csrf):
    semear(("Aluno Um", "a1@exemplo.com", "Direito"))
    dados = {} if csrf is None else {"csrf": csrf}
    assert logado.post(f"/admin/inscricoes/{ids()[0]}/remover", data=dados).status_code == 403
    assert len(ids()) == 1


def test_remover_id_inexistente_so_redireciona(logado, csrf_atual):
    r = logado.post("/admin/inscricoes/999/remover", data={"csrf": csrf_atual()})
    assert r.status_code == 303


@pytest.mark.parametrize("inscricao_id", ["0", "-1", str(2**31), "99999999999999999999", "abc"])
def test_remover_id_fora_do_intervalo_e_422(logado, csrf_atual, inscricao_id):
    r = logado.post(f"/admin/inscricoes/{inscricao_id}/remover", data={"csrf": csrf_atual()})
    assert r.status_code == 422


def test_csv_exige_sessao(client, admin):
    assert client.get("/admin/inscricoes.csv").status_code == 401


def test_csv_do_admin(logado):
    semear(("Aluno Um", "a1@exemplo.com", "Direito"), ("=1+1", "a2@exemplo.com", "Design"))
    r = logado.get("/admin/inscricoes.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == 'attachment; filename="inscritos-minicurso.csv"'
    assert r.headers["cache-control"] == "no-store"
    assert r.content.startswith(b"\xef\xbb\xbf")
    texto = r.content.decode("utf-8-sig")
    assert "Aluno Um;a1@exemplo.com;Direito;2º;Nenhuma;" in texto and "'=1+1;" in texto


def test_csv_ignora_o_filtro_e_exporta_todos(logado):
    semear(("Aluno Um", "a1@exemplo.com", "Direito"), ("Aluno Dois", "a2@exemplo.com", "Design"))
    assert logado.get("/admin/inscricoes.csv", params={"curso": "Direito"}).text.count("\r\n") == 3
