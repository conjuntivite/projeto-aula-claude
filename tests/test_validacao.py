import pytest
from pydantic import ValidationError

from app.validacao import CURSOS, Inscricao


def valido(**o):
    d = {"nome": "Aluno Teste", "email": "teste1@exemplo.com", "curso": "Direito",
         "periodo": 3, "experiencia": "basica", "consentimento": True}
    d.update(o)
    return d


def campos_invalidos(**o):
    with pytest.raises(ValidationError) as e:
        Inscricao(**valido(**o))
    return {err["loc"][0] for err in e.value.errors()}


def test_dados_validos_passam_e_normalizam_email():
    i = Inscricao(**valido(email="  TESTE1@Exemplo.com ", nome="  Aluno Teste "))
    assert i.nome == "Aluno Teste"
    assert i.email == "TESTE1@Exemplo.com"
    assert i.email_normalizado == "teste1@exemplo.com"


@pytest.mark.parametrize("nome", ["", "  ab ", "x" * 101])
def test_nome_fora_do_tamanho(nome):
    assert campos_invalidos(nome=nome) == {"nome"}


@pytest.mark.parametrize("email", ["sem-arroba", "a@b", "a b@c.co", "a@b.co\nb@c.co", "a@" + "b" * 250 + ".co"])
def test_email_invalido(email):
    assert campos_invalidos(email=email) == {"email"}


def test_curso_fora_da_lista():
    assert campos_invalidos(curso="Invalido") == {"curso"}
    assert "Outro" in CURSOS


@pytest.mark.parametrize("periodo", [0, 11, -1, "3", 3.5, True, None, [3]])
def test_periodo_invalido(periodo):
    assert campos_invalidos(periodo=periodo) == {"periodo"}


@pytest.mark.parametrize("exp", ["guru", "", "constructor", "toString", "__proto__", "hasOwnProperty", ["basica"], None])
def test_experiencia_invalida(exp):
    assert campos_invalidos(experiencia=exp) == {"experiencia"}


@pytest.mark.parametrize("valor", [False, "true", 1, None])
def test_consentimento_precisa_ser_true(valor):
    assert campos_invalidos(consentimento=valor) == {"consentimento"}


def test_campo_extra_e_recusado():
    assert campos_invalidos(admin=True) == {"admin"}


def test_campo_obrigatorio_ausente():
    d = valido()
    del d["email"]
    with pytest.raises(ValidationError):
        Inscricao(**d)
