import csv
import io

import pytest

from app.csv_export import gerar_csv, neutralizar


def linha(**o):
    d = {"nome": "Aluno Teste", "email": "teste1@exemplo.com", "curso": "Direito", "periodo": 3,
         "experiencia": "basica", "criado_em": "2026-10-01T12:00:00+00:00"}
    d.update(o)
    return d


def ler(texto):
    assert texto.startswith("﻿")
    return list(csv.reader(io.StringIO(texto[1:], newline=""), delimiter=";"))


def test_cabecalho_separador_e_linha():
    texto = gerar_csv([linha()])
    assert texto[1:].split("\r\n")[0] == "Nome;E-mail;Curso;Período;Experiência com IA;Inscrito em"
    assert ler(texto)[1] == ["Aluno Teste", "teste1@exemplo.com", "Direito", "3º", "Básica", "2026-10-01T12:00:00+00:00"]


def test_lista_vazia_tem_so_o_cabecalho():
    assert len(ler(gerar_csv([]))) == 1


@pytest.mark.parametrize("inicio", ["=", "+", "-", "@", "\t", "\r"])
def test_neutraliza_inicio_de_formula(inicio):
    assert neutralizar(f"{inicio}1+1") == f"'{inicio}1+1"


def test_nao_altera_texto_comum():
    assert neutralizar("Ana") == "Ana"
    assert neutralizar("a-b") == "a-b"


def test_conteudo_hostil_reabre_identico():
    nome = 'Ana; "Bia"\nCarla 😀 ção'
    assert ler(gerar_csv([linha(nome=nome)]))[1][0] == nome


def test_formula_sai_com_apostrofo_e_reabre_com_ele():
    formula = '=HYPERLINK("http://x";"y")'
    assert ler(gerar_csv([linha(nome=formula)]))[1][0] == "'" + formula


@pytest.mark.parametrize("campo", ["nome", "email", "curso"])
def test_neutraliza_todos_os_campos_de_texto(campo):
    assert ler(gerar_csv([linha(**{campo: "=1+1"})]))[1][["nome", "email", "curso"].index(campo)] == "'=1+1"
