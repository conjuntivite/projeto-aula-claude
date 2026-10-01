# Backend de inscrição com área de admin — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar a página de inscrição num sistema FastAPI + SQLite em que o público só envia a inscrição e apenas um admin autenticado vê a lista e exporta o CSV.

**Architecture:** Um único app FastAPI serve a página pública (estáticos), `POST /api/inscricoes` e o `/admin` (Jinja2, HTML no servidor). `sqlite3` da biblioteca padrão com SQL parametrizado, Pydantic para validar, sessão no servidor (hash SHA-256 do token), senha com Argon2id, CSRF por sessão, autorização negada por padrão no router do admin.

**Tech Stack:** Python 3.14 (instalado: 3.14.5), FastAPI, Uvicorn, Jinja2, python-multipart, argon2-cffi, pytest, httpx; JS puro no front (testes com Node 24).

**Spec:** `docs/superpowers/specs/2026-10-01-backend-admin-design.md` (evolui `2026-10-01-inscricao-minicurso-design.md`).

## Global Constraints

- Sem ORM, sem CORS, sem JavaScript inline nem `style=` inline nos HTML (a CSP é `default-src 'self'; frame-ancestors 'none'; form-action 'self'`).
- Todo SQL é parametrizado (`?` ou `:nome`); nunca montar SQL com f-string ou concatenação.
- Jinja2 com autoescape ligado (padrão de `Jinja2Templates` para `.html`); nunca usar `|safe`.
- Mensagens ao usuário em pt-BR; nomes de código em pt-BR sem acento, como no resto do projeto.
- Nenhuma senha em código de produção, arquivo de configuração ou repositório. Senhas dos testes são valores descartáveis que só existem em `tests/`.
- Dados de teste sempre fictícios (`Aluno Teste`, `teste1@exemplo.com`).
- Datas gravadas como ISO UTC com `timespec="seconds"` (via `db.agora()`), para a comparação de texto ordenar certo.
- Configuração só por `DATABASE_PATH` e `COOKIE_SECURE` (lidas na hora da chamada, não no import).
- Servidor local: `uvicorn app.main:app --host 127.0.0.1`. Comandos abaixo usam Git Bash no Windows (`.venv/Scripts/python`); em Linux/macOS troque por `.venv/bin/python`.
- Commits terminam com a linha `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

Entradas que a spec implica mas nenhum teste "óbvio" cobre, em ordem de probabilidade de morder. Cada uma tem teste na tarefa dona.

1. **Corpo JSON malformado, vazio, `null`, lista, ou campos com tipo errado** (`periodo: "3"`, `true`, `null`, lista; `email` como lista) em `POST /api/inscricoes`: deve responder `422` com JSON de erros em pt-BR, nunca `500`, nunca ecoar o valor enviado. → Tarefa 6.
2. **Conteúdo hostil no CSV** (nome com `;`, aspas, quebra de linha, emoji, fórmula `=HYPERLINK(...)`, tab ou CR iniciais): o arquivo tem de reabrir idêntico ao original, e fórmulas saem com apóstrofo. → Tarefa 5.
3. **Cookie de sessão e token CSRF adulterados** (vazio, 5000 caracteres, não ASCII, token plausível mas inexistente, CSRF não ASCII): tratar como não autenticado ou `403`, nunca `500` (`hmac.compare_digest` explode com `str` não ASCII). → Tarefas 3 e 7.
4. **Filtro `?curso=` e id de remoção fora do esperado** (valor desconhecido, `' OR 1=1 --`, parâmetro repetido; id `0`, negativo ou maior que 2³¹): ignorar o filtro, ou `422`; nunca `500` (id gigante estoura o `INTEGER` do SQLite). → Tarefa 8.
5. **Mesmo e-mail com grafias diferentes e envio repetido** (maiúsculas, espaços nas pontas, dois envios seguidos): uma única linha no banco e resposta idêntica à de uma inscrição nova. → Tarefas 1 e 6.

---

## File Structure

```
.gitignore  pytest.ini  requirements.txt  requirements-dev.txt  README.md
criar_admin.py                    # CLI: cria o admin (getpass)
app/
  __init__.py
  config.py                       # DATABASE_PATH, COOKIE_SECURE
  db.py                           # conexão, schema, consultas
  validacao.py                    # modelo Pydantic, CURSOS, mensagens de erro
  seguranca.py                    # Argon2id, sessões, CSRF, limites de tentativa
  csv_export.py                   # gerar_csv
  rotas_publicas.py               # POST /api/inscricoes
  rotas_admin.py                  # /admin/*
  main.py                         # criar_app(), cabeçalhos, handlers, estáticos
  templates/ base.html login.html admin.html
publico/                          # index.html style.css app.js admin.js (servidos)
tests/
  conftest.py  test_db.py  test_validacao.py  test_seguranca.py  test_cli.py
  test_csv.py  test_publico.py  test_admin_login.py  test_admin_lista.py
  front/ teste.js teste.html      # testes do JS (Node ou navegador)
```

Cada arquivo tem uma responsabilidade: `db.py` só fala SQL; `seguranca.py` só cripto, sessão e limites; as rotas só orquestram.

---

### Task 1: Ambiente, configuração e banco

**Files:**
- Create: `.gitignore`, `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `app/__init__.py`, `app/config.py`, `app/db.py`, `tests/conftest.py`, `tests/test_db.py`

**Interfaces:**
- Produces:
  - `config.database_path() -> Path`, `config.cookie_secure() -> bool`
  - `db.agora() -> str`, `db.agora_mais(segundos: int) -> str`
  - `db.conectar() -> sqlite3.Connection` (Row factory, `foreign_keys=ON`), `db.iniciar() -> None`, `db.transacao()` (context manager: commit/rollback/close)
  - `db.inserir_inscricao(con, d: dict) -> bool` (`d` com `nome, email, email_normalizado, curso, periodo, experiencia, consentimento_em, versao_consentimento`; `False` se o e-mail normalizado já existe)
  - `db.listar_inscricoes(con, curso: str | None = None) -> list[Row]`, `db.contar(con) -> int`, `db.remover_inscricao(con, inscricao_id: int) -> bool`
  - `db.criar_admin_db(con, usuario: str, senha_hash: str) -> int`, `db.obter_admin(con, usuario: str) -> Row | None`, `db.atualizar_hash(con, admin_id: int, senha_hash: str) -> None`
  - Fixtures `banco` (banco temporário já iniciado) e `con` (conexão com transação).

- [ ] **Step 1: Salvar o front-end atual como linha de base e criar o ambiente**

```bash
git add app.js index.html style.css teste.html teste.js docs/superpowers/specs/2026-10-01-inscricao-minicurso-design.md
git commit -m "feat: página de inscrição só de front-end (localStorage)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Criar `.gitignore`:

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
*.db
*.db-journal
```

Criar `requirements.txt`:

```
fastapi>=0.115
uvicorn>=0.30
jinja2>=3.1
python-multipart>=0.0.9
argon2-cffi>=23.1
```

Criar `requirements-dev.txt`:

```
-r requirements.txt
pytest>=8
httpx>=0.27
```

Criar `pytest.ini`:

```
[pytest]
pythonpath = .
testpaths = tests
```

Criar `app/__init__.py` vazio. Instalar:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -c "import fastapi, uvicorn, jinja2, argon2, multipart, pytest, httpx; print('deps ok')"
```
Expected: `deps ok`. Se algum pacote não instalar no Python 3.14, **pare e reporte** (não troque de versão sem avisar).

- [ ] **Step 2: Escrever o teste que falha**

Criar `tests/conftest.py`:

```python
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
```

Criar `tests/test_db.py`:

```python
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
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_db.py -v`
Expected: erro de coleta `ImportError: cannot import name 'config'` (módulos ainda não existem).

- [ ] **Step 4: Implementar**

Criar `app/config.py`:

```python
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def database_path() -> Path:
    return Path(os.environ.get("DATABASE_PATH", RAIZ / "inscricoes.db"))


def cookie_secure() -> bool:
    # Decisão 5: Secure só funciona em HTTPS; em http://localhost fica desligado.
    return os.environ.get("COOKIE_SECURE", "0") == "1"
```

Criar `app/db.py`:

```python
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from app import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS inscricoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  email TEXT NOT NULL,
  email_normalizado TEXT NOT NULL UNIQUE,
  curso TEXT NOT NULL,
  periodo INTEGER NOT NULL CHECK (periodo BETWEEN 1 AND 10),
  experiencia TEXT NOT NULL CHECK (experiencia IN ('nenhuma', 'basica', 'avancada')),
  consentimento_em TEXT NOT NULL,
  versao_consentimento TEXT NOT NULL,
  criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS admins (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario TEXT NOT NULL UNIQUE,
  senha_hash TEXT NOT NULL,
  criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessoes (
  token_hash TEXT PRIMARY KEY,
  admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
  csrf_token TEXT NOT NULL,
  criada_em TEXT NOT NULL,
  expira_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tentativas_login (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  usuario TEXT NOT NULL,
  ip TEXT NOT NULL,
  criada_em TEXT NOT NULL
);
"""


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def agora_mais(segundos: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=segundos)).isoformat(timespec="seconds")


def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(config.database_path())
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def iniciar() -> None:
    con = conectar()
    try:
        con.executescript(SCHEMA)
    finally:
        con.close()


@contextmanager
def transacao():
    con = conectar()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def inserir_inscricao(con, d: dict) -> bool:
    # Decisão 10: SQL parametrizado. ON CONFLICT trata o e-mail repetido sem erro
    # e sem condição de corrida (a UNIQUE decide, não uma consulta prévia).
    cur = con.execute(
        "INSERT INTO inscricoes (nome, email, email_normalizado, curso, periodo, experiencia,"
        " consentimento_em, versao_consentimento, criado_em)"
        " VALUES (:nome, :email, :email_normalizado, :curso, :periodo, :experiencia,"
        " :consentimento_em, :versao_consentimento, :criado_em)"
        " ON CONFLICT(email_normalizado) DO NOTHING",
        {**d, "criado_em": agora()},
    )
    return cur.rowcount == 1


def listar_inscricoes(con, curso: str | None = None) -> list:
    if curso:
        return con.execute("SELECT * FROM inscricoes WHERE curso = ? ORDER BY id", (curso,)).fetchall()
    return con.execute("SELECT * FROM inscricoes ORDER BY id").fetchall()


def contar(con) -> int:
    return con.execute("SELECT COUNT(*) FROM inscricoes").fetchone()[0]


def remover_inscricao(con, inscricao_id: int) -> bool:
    return con.execute("DELETE FROM inscricoes WHERE id = ?", (inscricao_id,)).rowcount == 1


def criar_admin_db(con, usuario: str, senha_hash: str) -> int:
    cur = con.execute(
        "INSERT INTO admins (usuario, senha_hash, criado_em) VALUES (?, ?, ?)",
        (usuario, senha_hash, agora()),
    )
    return cur.lastrowid


def obter_admin(con, usuario: str):
    return con.execute("SELECT * FROM admins WHERE usuario = ?", (usuario,)).fetchone()


def atualizar_hash(con, admin_id: int, senha_hash: str) -> None:
    con.execute("UPDATE admins SET senha_hash = ? WHERE id = ?", (senha_hash, admin_id))
```

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_db.py -v`
Expected: 11 passed.

- [ ] **Step 6: Commit**

```bash
git add .gitignore requirements.txt requirements-dev.txt pytest.ini app tests
git commit -m "feat: configuração e camada de banco SQLite" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Validação da inscrição (servidor)

**Files:**
- Create: `app/validacao.py`, `tests/test_validacao.py`

**Interfaces:**
- Produces:
  - `CURSOS: list[str]`, `EXPERIENCIAS: dict[str, str]`, `VERSAO_CONSENTIMENTO: str`, `MENSAGENS_ERRO: dict[str, str]`
  - `class Inscricao(BaseModel)` com `nome, email, curso, periodo: int, experiencia, consentimento: bool` e a propriedade `email_normalizado -> str`

- [ ] **Step 1: Escrever o teste que falha**

Criar `tests/test_validacao.py`:

```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_validacao.py -v`
Expected: erro de coleta `ModuleNotFoundError: No module named 'app.validacao'`.

- [ ] **Step 3: Implementar**

Criar `app/validacao.py`:

```python
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CURSOS = ["Administração", "Ciência da Computação", "Direito", "Engenharia", "Medicina",
          "Psicologia", "Design", "Comunicação", "Outro"]
EXPERIENCIAS = {"nenhuma": "Nenhuma", "basica": "Básica", "avancada": "Avançada"}
# Mude esta versão sempre que o texto do consentimento em publico/index.html mudar.
VERSAO_CONSENTIMENTO = "2026-10-01"

EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")

# Mensagens por campo. A resposta 422 usa estas frases e nunca ecoa o valor enviado.
MENSAGENS_ERRO = {
    "nome": "Informe seu nome completo (3 a 100 caracteres).",
    "email": "Informe um e-mail válido, como nome@exemplo.com.",
    "curso": "Selecione seu curso.",
    "periodo": "Selecione seu período (1º a 10º).",
    "experiencia": "Escolha seu nível de experiência com IA.",
    "consentimento": "É necessário consentir com o uso dos dados para se inscrever.",
    "_geral": "Requisição inválida.",
}


class Inscricao(BaseModel):
    # Decisão 10: o servidor valida tudo; extra="forbid" recusa campos que não existem.
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    nome: str = Field(min_length=3, max_length=100)
    email: str = Field(max_length=254)
    curso: str
    periodo: int = Field(strict=True, ge=1, le=10)
    experiencia: Literal["nenhuma", "basica", "avancada"]
    consentimento: bool = Field(strict=True)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        if not EMAIL_RE.fullmatch(v):
            raise ValueError("e-mail inválido")
        return v

    @field_validator("curso")
    @classmethod
    def _curso(cls, v: str) -> str:
        if v not in CURSOS:
            raise ValueError("curso inválido")
        return v

    @field_validator("consentimento")
    @classmethod
    def _consentimento(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("consentimento obrigatório")
        return v

    @property
    def email_normalizado(self) -> str:
        return self.email.lower()
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_validacao.py -v`
Expected: todos passam. Se algum caso do `parametrize` falhar por diferença de versão do Pydantic (por exemplo `3.5` ou `True` aceitos em `periodo`), corrija o **modelo** (não o teste) até recusar.

- [ ] **Step 5: Commit**

```bash
git add app/validacao.py tests/test_validacao.py
git commit -m "feat: validação da inscrição no servidor (Pydantic)" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Senha, sessão, CSRF e criação do admin

**Files:**
- Create: `app/seguranca.py`, `criar_admin.py`, `tests/test_seguranca.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `db.agora`, `db.agora_mais`, `db.criar_admin_db`, `db.obter_admin` (Tarefa 1).
- Produces (em `app/seguranca.py`):
  - `hash_senha(senha: str) -> str`, `verificar_senha(hash_: str, senha: str) -> bool` (nunca lança), `precisa_rehash(hash_: str) -> bool`, `HASH_FALSO: str`
  - `class UsuarioExistente(Exception)`, `criar_admin(con, usuario: str, senha: str) -> int` (`ValueError` se usuário vazio/longo ou senha < 12 ou > 1024)
  - `SESSAO_SEGUNDOS = 7200`; `criar_sessao(con, admin_id: int) -> tuple[str, str]` (token, csrf); `obter_sessao(con, token: str | None) -> dict | None` com chaves `admin_id, csrf_token, usuario`; `apagar_sessao(con, token) -> None`; `limpar_expiradas(con) -> None`
  - `csrf_valido(esperado: str, recebido: str | None) -> bool`
- Produces (em `criar_admin.py`): `main() -> int`

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_seguranca.py`:

```python
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
```

Criar `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_seguranca.py tests/test_cli.py -v`
Expected: erro de coleta `ImportError: cannot import name 'seguranca'` / `No module named 'criar_admin'`.

- [ ] **Step 3: Implementar `app/seguranca.py`**

```python
import hashlib
import hmac
import secrets
import sqlite3

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app import db

_ph = PasswordHasher()

SENHA_MINIMA = 12
SENHA_MAXIMA = 1024
SESSAO_SEGUNDOS = 2 * 3600


class UsuarioExistente(Exception):
    pass


# Decisão 1: Argon2id, sal aleatório embutido no hash. Se o banco vazar, as senhas
# não são lidas, e o hash é lento de propósito para frustrar tentativa em massa.
def hash_senha(senha: str) -> str:
    return _ph.hash(senha)


def verificar_senha(hash_: str, senha: str) -> bool:
    try:
        return _ph.verify(hash_, senha)
    except (VerificationError, InvalidHashError):
        return False


def precisa_rehash(hash_: str) -> bool:
    return _ph.check_needs_rehash(hash_)


# Decisão 2: usado quando o usuário não existe, para o tempo de resposta ser parecido
# e não revelar quais usuários existem.
HASH_FALSO = _ph.hash("hash-falso-para-igualar-o-tempo-de-resposta")


def criar_admin(con, usuario: str, senha: str) -> int:
    usuario = usuario.strip().lower()
    if not usuario or len(usuario) > 100:
        raise ValueError("Usuário inválido (1 a 100 caracteres).")
    if len(senha) < SENHA_MINIMA:
        raise ValueError(f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres.")
    if len(senha) > SENHA_MAXIMA:
        raise ValueError(f"A senha pode ter no máximo {SENHA_MAXIMA} caracteres.")
    try:
        return db.criar_admin_db(con, usuario, hash_senha(senha))
    except sqlite3.IntegrityError as e:
        raise UsuarioExistente(usuario) from e


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8", "replace")).hexdigest()


# Decisão 4: o cookie leva um token aleatório; o banco guarda só o SHA-256 dele.
# Quem lê o banco não consegue usar as sessões. Cada login gera token novo.
def criar_sessao(con, admin_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    con.execute(
        "INSERT INTO sessoes (token_hash, admin_id, csrf_token, criada_em, expira_em) VALUES (?, ?, ?, ?, ?)",
        (_hash_token(token), admin_id, csrf, db.agora(), db.agora_mais(SESSAO_SEGUNDOS)),
    )
    return token, csrf


def obter_sessao(con, token: str | None) -> dict | None:
    if not token or len(token) > 200:
        return None
    linha = con.execute(
        "SELECT s.admin_id, s.csrf_token, a.usuario FROM sessoes s"
        " JOIN admins a ON a.id = s.admin_id WHERE s.token_hash = ? AND s.expira_em > ?",
        (_hash_token(token), db.agora()),
    ).fetchone()
    return dict(linha) if linha else None


def apagar_sessao(con, token: str | None) -> None:
    if token:
        con.execute("DELETE FROM sessoes WHERE token_hash = ?", (_hash_token(token),))


def limpar_expiradas(con) -> None:
    con.execute("DELETE FROM sessoes WHERE expira_em <= ?", (db.agora(),))


# Decisão 6: comparação em tempo constante. Codifica antes porque compare_digest
# lança TypeError com texto não ASCII.
def csrf_valido(esperado: str, recebido: str | None) -> bool:
    if not recebido:
        return False
    return hmac.compare_digest(esperado.encode("utf-8", "replace"), recebido.encode("utf-8", "replace"))
```

- [ ] **Step 4: Implementar `criar_admin.py`**

```python
import getpass
import sys

from app import db, seguranca


def main() -> int:
    db.iniciar()
    usuario = input("Usuário: ").strip()
    senha = getpass.getpass(f"Senha (mínimo {seguranca.SENHA_MINIMA} caracteres): ")
    if getpass.getpass("Repita a senha: ") != senha:
        print("As senhas não conferem.")
        return 1
    try:
        with db.transacao() as con:
            seguranca.criar_admin(con, usuario, senha)
    except seguranca.UsuarioExistente:
        print("Esse usuário já existe.")
        return 1
    except ValueError as e:
        print(e)
        return 1
    print("Admin criado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_seguranca.py tests/test_cli.py -v`
Expected: todos passam.

- [ ] **Step 6: Commit**

```bash
git add app/seguranca.py criar_admin.py tests/test_seguranca.py tests/test_cli.py
git commit -m "feat: hash Argon2id, sessões no servidor, CSRF e criar_admin.py" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Limite de tentativas de login e de envios por IP

**Files:**
- Modify: `app/seguranca.py` (acrescentar ao final)
- Test: `tests/test_seguranca.py` (acrescentar ao final)

**Interfaces:**
- Consumes: `db.agora`, `db.agora_mais`, tabela `tentativas_login` (Tarefa 1).
- Produces (em `app/seguranca.py`):
  - `MAX_FALHAS = 5`, `JANELA_LOGIN_S = 900`
  - `normalizar_usuario(usuario: str) -> str` (`strip().lower()[:100]`)
  - `registrar_falha(con, usuario: str, ip: str) -> None`, `bloqueado(con, usuario: str, ip: str) -> bool`, `limpar_falhas(con, usuario: str, ip: str) -> None`
  - `class LimitadorPorIp(maximo: int, janela_s: float, relogio=time.monotonic)` com `permitir(ip: str) -> bool`
  - `limpar_expiradas(con)` passa a apagar também tentativas fora da janela.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao final de `tests/test_seguranca.py`:

```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_seguranca.py -v`
Expected: os 7 testes novos falham com `AttributeError: module 'app.seguranca' has no attribute 'registrar_falha'` (ou `JANELA_LOGIN_S`/`LimitadorPorIp`); os anteriores seguem passando.

- [ ] **Step 3: Implementar**

Em `app/seguranca.py`: adicionar `import time` e `from collections import defaultdict, deque` ao topo, substituir `limpar_expiradas` pela versão abaixo e acrescentar o restante ao final do arquivo.

```python
def limpar_expiradas(con) -> None:
    con.execute("DELETE FROM sessoes WHERE expira_em <= ?", (db.agora(),))
    con.execute("DELETE FROM tentativas_login WHERE criada_em <= ?", (db.agora_mais(-JANELA_LOGIN_S),))
```

```python
# Decisão 3: 5 falhas por usuário e IP em 15 minutos bloqueiam temporariamente. A chave
# é o texto digitado (exista o usuário ou não), então o bloqueio não revela quem existe.
MAX_FALHAS = 5
JANELA_LOGIN_S = 15 * 60


def normalizar_usuario(usuario: str) -> str:
    return usuario.strip().lower()[:100]


def registrar_falha(con, usuario: str, ip: str) -> None:
    con.execute("INSERT INTO tentativas_login (usuario, ip, criada_em) VALUES (?, ?, ?)",
                (normalizar_usuario(usuario), ip, db.agora()))


def bloqueado(con, usuario: str, ip: str) -> bool:
    n = con.execute(
        "SELECT COUNT(*) FROM tentativas_login WHERE usuario = ? AND ip = ? AND criada_em > ?",
        (normalizar_usuario(usuario), ip, db.agora_mais(-JANELA_LOGIN_S)),
    ).fetchone()[0]
    return n >= MAX_FALHAS


def limpar_falhas(con, usuario: str, ip: str) -> None:
    con.execute("DELETE FROM tentativas_login WHERE usuario = ? AND ip = ?", (normalizar_usuario(usuario), ip))


# Decisão 10: limite de envios da inscrição pública, por IP, em memória.
# ponytail: zera ao reiniciar e não é compartilhado entre processos; em produção, usar um
# armazenamento compartilhado (Redis ou tabela).
class LimitadorPorIp:
    def __init__(self, maximo: int, janela_s: float, relogio=time.monotonic):
        self._maximo, self._janela, self._relogio = maximo, janela_s, relogio
        self._eventos: dict[str, deque] = defaultdict(deque)

    def permitir(self, ip: str) -> bool:
        agora = self._relogio()
        fila = self._eventos[ip]
        while fila and agora - fila[0] > self._janela:
            fila.popleft()
        if len(fila) >= self._maximo:
            return False
        fila.append(agora)
        return True
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_seguranca.py -v`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add app/seguranca.py tests/test_seguranca.py
git commit -m "feat: limite de tentativas de login e de envios por IP" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Exportação CSV no servidor

**Files:**
- Create: `app/csv_export.py`, `tests/test_csv.py`

**Interfaces:**
- Consumes: `validacao.EXPERIENCIAS` (Tarefa 2).
- Produces: `neutralizar(valor) -> str`, `gerar_csv(inscritos: Iterable[Mapping]) -> str` (as linhas precisam ter `nome, email, curso, periodo, experiencia, criado_em`; aceita `dict` ou `sqlite3.Row`).

- [ ] **Step 1: Escrever o teste que falha**

Criar `tests/test_csv.py`:

```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_csv.py -v`
Expected: erro de coleta `ModuleNotFoundError: No module named 'app.csv_export'`.

- [ ] **Step 3: Implementar**

Criar `app/csv_export.py`:

```python
import csv
import io

from app.validacao import EXPERIENCIAS

CABECALHO = ["Nome", "E-mail", "Curso", "Período", "Experiência com IA", "Inscrito em"]


def neutralizar(valor) -> str:
    # Decisão 8 (CSV): célula que começa com = + - @ tab ou CR vira fórmula no Excel.
    # O apóstrofo força texto. Protege quem abre o arquivo.
    s = str(valor)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def gerar_csv(inscritos) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(CABECALHO)
    for i in inscritos:
        w.writerow([neutralizar(i["nome"]), neutralizar(i["email"]), neutralizar(i["curso"]),
                    f"{i['periodo']}º", EXPERIENCIAS[i["experiencia"]], i["criado_em"]])
    return "﻿" + buf.getvalue()  # BOM: o Excel pt-BR reconhece UTF-8
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_csv.py -v`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add app/csv_export.py tests/test_csv.py
git commit -m "feat: exportação CSV no servidor com proteção contra fórmulas" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: App FastAPI, cabeçalhos e inscrição pública

**Files:**
- Create: `app/main.py`, `app/rotas_publicas.py`, `tests/test_publico.py`
- Move: `app.js`, `index.html`, `style.css` → `publico/`; `teste.js`, `teste.html` → `tests/front/`
- Modify: `tests/conftest.py` (fixture `client`)

**Interfaces:**
- Consumes: `db.*`, `validacao.Inscricao`, `validacao.MENSAGENS_ERRO`, `validacao.VERSAO_CONSENTIMENTO`, `seguranca.LimitadorPorIp`.
- Produces:
  - `criar_app() -> FastAPI` e `app` em `app/main.py`; `app.state.limitador` (10 envios/60 s por IP).
  - `rotas_publicas.router` (`POST /api/inscricoes`), `rotas_publicas.ip_do_cliente(request) -> str`, `rotas_publicas.MENSAGEM_SUCESSO`.
  - Fixture `client`: `TestClient(criar_app(), follow_redirects=False)` com banco temporário.
  - Resposta `422`: `{"erros": {campo: mensagem}}` (campo `_geral` para corpo ilegível).

- [ ] **Step 1: Reorganizar os arquivos do front-end**

```bash
mkdir -p publico tests/front
git mv app.js index.html style.css publico/
git mv teste.js teste.html tests/front/
```

Em `tests/front/teste.js`, trocar `require('./app.js')` por `require('../../publico/app.js')`. Em `tests/front/teste.html`, trocar `src="app.js"` por `src="../../publico/app.js"`.

Run: `node tests/front/teste.js | tail -2`
Expected: `31/31 passaram`.

- [ ] **Step 2: Escrever os testes que falham**

Acrescentar ao final de `tests/conftest.py`:

```python
from fastapi.testclient import TestClient


@pytest.fixture
def client(banco):
    from app.main import criar_app

    with TestClient(criar_app(), follow_redirects=False) as c:
        yield c
```

Criar `tests/test_publico.py`:

```python
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
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_publico.py -v`
Expected: falha ao montar a fixture `client`: `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 4: Implementar a rota pública**

Criar `app/rotas_publicas.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Request

from app import db
from app.validacao import VERSAO_CONSENTIMENTO, Inscricao

router = APIRouter()

# Decisão 10: resposta neutra. Quem se inscreve duas vezes recebe a mesma resposta de
# quem se inscreve pela primeira vez, então ninguém descobre se um e-mail já está inscrito.
MENSAGEM_SUCESSO = "Recebemos sua inscrição. Obrigado!"


def ip_do_cliente(request: Request) -> str:
    # Usa o IP da conexão. X-Forwarded-For não é confiado: o cliente pode forjá-lo.
    return request.client.host if request.client else "desconhecido"


def limitar_envio(request: Request) -> None:
    if not request.app.state.limitador.permitir(ip_do_cliente(request)):
        raise HTTPException(status_code=429, detail="Muitas tentativas. Tente novamente em instantes.")


@router.post("/api/inscricoes", status_code=201, dependencies=[Depends(limitar_envio)])
def inscrever(dados: Inscricao):
    with db.transacao() as con:
        db.inserir_inscricao(con, {
            "nome": dados.nome, "email": dados.email, "email_normalizado": dados.email_normalizado,
            "curso": dados.curso, "periodo": dados.periodo, "experiencia": dados.experiencia,
            "consentimento_em": db.agora(), "versao_consentimento": VERSAO_CONSENTIMENTO,
        })
    return {"mensagem": MENSAGEM_SUCESSO}
```

- [ ] **Step 5: Implementar o app**

Criar `app/main.py`:

```python
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.rotas_publicas import router as rotas_publicas
from app.seguranca import LimitadorPorIp
from app.validacao import MENSAGENS_ERRO

PUBLICO = Path(__file__).resolve().parent.parent / "publico"

# Decisão 9: CSP restringe de onde a página carrega recursos (defesa extra contra XSS),
# proíbe ser embutida em outro site (clickjacking) e limita para onde formulários enviam.
CSP = "default-src 'self'; frame-ancestors 'none'; form-action 'self'"


@asynccontextmanager
async def lifespan(_app):
    db.iniciar()
    yield


async def cabecalhos(request: Request, call_next):
    resposta = await call_next(request)
    resposta.headers["Content-Security-Policy"] = CSP
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    resposta.headers["Referrer-Policy"] = "no-referrer"
    # Decisão 8: dados pessoais não ficam em cache do navegador nem de proxies.
    if request.url.path.startswith(("/admin", "/api")):
        resposta.headers["Cache-Control"] = "no-store"
    return resposta


async def erro_validacao(_request: Request, exc: RequestValidationError):
    # Só devolvemos o nome do campo e uma frase fixa. Nunca o valor enviado.
    erros: dict[str, str] = {}
    for e in exc.errors():
        loc = e.get("loc", ())
        campo = loc[1] if len(loc) > 1 and isinstance(loc[1], str) else "_geral"
        erros[campo] = MENSAGENS_ERRO.get(campo, "Valor inválido.")
    return JSONResponse({"erros": erros}, status_code=422)


def criar_app() -> FastAPI:
    # Decisão 11: documentação da API desligada; debug desligado (erro 500 genérico).
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.limitador = LimitadorPorIp(maximo=10, janela_s=60)
    app.middleware("http")(cabecalhos)
    app.add_exception_handler(RequestValidationError, erro_validacao)
    app.include_router(rotas_publicas)
    # Decisão 11: só publico/ é servido. Montado por último para não encobrir as rotas.
    app.mount("/", StaticFiles(directory=PUBLICO, html=True), name="publico")
    return app


app = criar_app()
```

- [ ] **Step 6: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest tests/test_publico.py -v`
Expected: todos passam. Rodar também `.venv/Scripts/python -m pytest -q` (tudo verde) e `node tests/front/teste.js | tail -1` (`31/31 passaram`).

- [ ] **Step 7: Commit**

```bash
git add app publico tests
git commit -m "feat: app FastAPI com inscrição pública, cabeçalhos de segurança e estáticos" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Login, logout e proteção do admin

**Files:**
- Create: `app/rotas_admin.py`, `app/templates/base.html`, `app/templates/login.html`, `app/templates/admin.html`, `tests/test_admin_login.py`
- Modify: `app/main.py`, `tests/conftest.py`, `publico/style.css`

**Interfaces:**
- Consumes: `db.*`, `seguranca.*` (Tarefas 1, 3, 4), `rotas_publicas.ip_do_cliente`, `config.cookie_secure`.
- Produces:
  - `rotas_admin.COOKIE = "sessao"`, `exigir_admin(request) -> dict` (`admin_id, csrf_token, usuario`), `class NaoAutenticado(Exception)`, `verificar_csrf(sessao: dict, recebido: str | None) -> None` (`HTTPException(403)`), `TEMPLATES`, `login_router` (público: `GET/POST /admin/login`), `router` (protegido, com `dependencies=[Depends(exigir_admin)]`: `GET /admin`, `POST /admin/logout`).
  - Fixtures `admin`, `senha`, `logar()`, `csrf_atual()`.

- [ ] **Step 1: Escrever os testes que falham**

Acrescentar ao final de `tests/conftest.py`:

```python
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
```

Criar `tests/test_admin_login.py`:

```python
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
    r = client.get("/admin", headers={"Cookie": cookie})
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_admin_login.py -v`
Expected: falha: `/admin/login` responde 404 (rotas ainda não existem), com `assert 404 == 303` e similares.

- [ ] **Step 3: Implementar as rotas do admin**

Criar `app/rotas_admin.py`:

```python
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import config, db, seguranca
from app.rotas_publicas import ip_do_cliente

COOKIE = "sessao"
# Autoescape do Jinja2 fica ligado para .html: dado do usuário nunca vira HTML.
TEMPLATES = Jinja2Templates(directory=Path(__file__).resolve().parent / "templates")

# Decisão 2: a mesma frase para usuário inexistente e senha errada.
MSG_LOGIN_INVALIDO = "Usuário ou senha inválidos."
MSG_BLOQUEADO = "Muitas tentativas. Tente novamente em alguns minutos."


class NaoAutenticado(Exception):
    pass


def exigir_admin(request: Request) -> dict:
    with db.transacao() as con:
        sessao = seguranca.obter_sessao(con, request.cookies.get(COOKIE))
    if sessao is None:
        raise NaoAutenticado()
    return sessao


def verificar_csrf(sessao: dict, recebido: str | None) -> None:
    # Decisão 6: token por sessão em campo oculto (SameSite=Strict já ajuda; os dois juntos).
    if not seguranca.csrf_valido(sessao["csrf_token"], recebido):
        raise HTTPException(status_code=403, detail="Token CSRF inválido.")


# Rotas públicas do admin: só o login.
login_router = APIRouter(prefix="/admin")

# Decisão 7: a dependência fica no router inteiro. Qualquer rota nova adicionada aqui
# nasce protegida; não dá para esquecer de proteger.
router = APIRouter(prefix="/admin", dependencies=[Depends(exigir_admin)])


@login_router.get("/login")
def pagina_login(request: Request):
    return TEMPLATES.TemplateResponse(request, "login.html", {"erro": None})


@login_router.post("/login")
def entrar(request: Request, usuario: str = Form(max_length=100), senha: str = Form(max_length=1024)):
    ip = ip_do_cliente(request)
    chave = seguranca.normalizar_usuario(usuario)
    with db.transacao() as con:
        if seguranca.bloqueado(con, chave, ip):
            return TEMPLATES.TemplateResponse(request, "login.html", {"erro": MSG_BLOQUEADO}, status_code=429)
        admin = db.obter_admin(con, chave)
        senha_hash = admin["senha_hash"] if admin else seguranca.HASH_FALSO
        senha_ok = seguranca.verificar_senha(senha_hash, senha)
        if admin is None or not senha_ok:
            seguranca.registrar_falha(con, chave, ip)
            return TEMPLATES.TemplateResponse(request, "login.html", {"erro": MSG_LOGIN_INVALIDO}, status_code=401)
        seguranca.limpar_falhas(con, chave, ip)
        seguranca.limpar_expiradas(con)
        seguranca.apagar_sessao(con, request.cookies.get(COOKIE))  # não deixa sessão antiga viva
        if seguranca.precisa_rehash(senha_hash):
            db.atualizar_hash(con, admin["id"], seguranca.hash_senha(senha))
        token, _csrf = seguranca.criar_sessao(con, admin["id"])
    resposta = RedirectResponse("/admin", status_code=303)
    # Decisão 5: HttpOnly (JS não lê o cookie), SameSite=Strict (outros sites não o enviam),
    # Path=/admin (só vai nas rotas do admin), Secure conforme COOKIE_SECURE.
    resposta.set_cookie(COOKIE, token, max_age=seguranca.SESSAO_SEGUNDOS, httponly=True,
                        samesite="strict", secure=config.cookie_secure(), path="/admin")
    return resposta


@router.get("")
def pagina_admin(request: Request, sessao: dict = Depends(exigir_admin)):
    return TEMPLATES.TemplateResponse(
        request, "admin.html", {"usuario": sessao["usuario"], "csrf": sessao["csrf_token"]})


@router.post("/logout")
def sair(request: Request, csrf: str = Form(""), sessao: dict = Depends(exigir_admin)):
    verificar_csrf(sessao, csrf)
    with db.transacao() as con:
        seguranca.apagar_sessao(con, request.cookies.get(COOKIE))
    resposta = RedirectResponse("/admin/login", status_code=303)
    resposta.delete_cookie(COOKIE, path="/admin")
    return resposta
```

- [ ] **Step 4: Criar os templates**

`app/templates/base.html`:

```html
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>{% block titulo %}Admin{% endblock %} — Minicurso</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <header class="topo"><h1>Área do administrador</h1></header>
  <main>{% block conteudo %}{% endblock %}</main>
</body>
</html>
```

`app/templates/login.html`:

```html
{% extends "base.html" %}
{% block titulo %}Entrar{% endblock %}
{% block conteudo %}
<section class="cartao" aria-labelledby="titulo-login">
  <h2 id="titulo-login">Entrar</h2>
  {% if erro %}<p class="resumo" role="alert">{{ erro }}</p>{% endif %}
  <form method="post" action="/admin/login">
    <div class="campo">
      <label for="usuario">Usuário</label>
      <input id="usuario" name="usuario" type="text" autocomplete="username" required maxlength="100">
    </div>
    <div class="campo">
      <label for="senha">Senha</label>
      <input id="senha" name="senha" type="password" autocomplete="current-password" required maxlength="1024">
    </div>
    <button type="submit" class="botao">Entrar</button>
  </form>
</section>
{% endblock %}
```

`app/templates/admin.html` (versão mínima; a lista entra na Tarefa 8):

```html
{% extends "base.html" %}
{% block titulo %}Inscritos{% endblock %}
{% block conteudo %}
<section class="cartao" aria-labelledby="titulo-lista">
  <div class="lista-topo">
    <h2 id="titulo-lista">Inscritos</h2>
    <form method="post" action="/admin/logout">
      <input type="hidden" name="csrf" value="{{ csrf }}">
      <button type="submit" class="botao secundario">Sair ({{ usuario }})</button>
    </form>
  </div>
</section>
{% endblock %}
```

Em `publico/style.css`, trocar a linha do seletor `input[type="text"], input[type="email"], select {` por:

```css
input[type="text"], input[type="email"], input[type="password"], select {
```

- [ ] **Step 5: Ligar ao app**

Em `app/main.py`: adicionar aos imports

```python
from fastapi.responses import JSONResponse, RedirectResponse

from app.rotas_admin import NaoAutenticado, login_router
from app.rotas_admin import router as rotas_admin
```

(ajustando a linha existente `from fastapi.responses import JSONResponse`), acrescentar a função

```python
async def nao_autenticado(request: Request, _exc: NaoAutenticado):
    # Decisão 7: páginas HTML vão para o login; POST e CSV recebem 401.
    if request.method == "GET" and not request.url.path.endswith(".csv"):
        return RedirectResponse("/admin/login", status_code=303)
    return JSONResponse({"detail": "Não autenticado."}, status_code=401)
```

e, em `criar_app()`, antes do `app.mount(...)`:

```python
    app.add_exception_handler(NaoAutenticado, nao_autenticado)
    app.include_router(login_router)
    app.include_router(rotas_admin)
```

- [ ] **Step 6: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest -q`
Expected: tudo verde (inclui `test_admin_login.py` e os testes anteriores).

- [ ] **Step 7: Commit**

```bash
git add app publico/style.css tests
git commit -m "feat: login, logout e proteção por padrão da área de admin" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Lista, filtro, remoção e CSV no admin

**Files:**
- Modify: `app/rotas_admin.py`, `app/templates/admin.html`, `app/templates/base.html`, `publico/style.css`
- Create: `publico/admin.js`, `tests/test_admin_lista.py`

**Interfaces:**
- Consumes: `rotas_admin.exigir_admin`, `verificar_csrf`, `TEMPLATES`, `router` (Tarefa 7); `db.listar_inscricoes`, `db.contar`, `db.remover_inscricao`; `csv_export.gerar_csv`; `validacao.CURSOS`, `EXPERIENCIAS`.
- Produces: `GET /admin?curso=`, `POST /admin/inscricoes/{inscricao_id}/remover`, `GET /admin/inscricoes.csv`.

- [ ] **Step 1: Escrever os testes que falham**

Criar `tests/test_admin_lista.py`:

```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python -m pytest tests/test_admin_lista.py -v`
Expected: falham (página mínima sem lista; rotas de remoção e CSV dão 404/405).

- [ ] **Step 3: Implementar as rotas**

Em `app/rotas_admin.py`, trocar os imports do topo para:

```python
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi import Path as CaminhoParam
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app import config, db, seguranca
from app.csv_export import gerar_csv
from app.rotas_publicas import ip_do_cliente
from app.validacao import CURSOS, EXPERIENCIAS
```

(`CaminhoParam` evita o choque de nome com `pathlib.Path`.)

Substituir a função `pagina_admin` por:

```python
@router.get("")
def pagina_admin(request: Request, curso: str = "", sessao: dict = Depends(exigir_admin)):
    # O filtro só aceita cursos da lista; qualquer outro valor é ignorado.
    if curso not in CURSOS:
        curso = ""
    with db.transacao() as con:
        total = db.contar(con)
        inscritos = [dict(r) for r in db.listar_inscricoes(con, curso or None)]
    return TEMPLATES.TemplateResponse(request, "admin.html", {
        "usuario": sessao["usuario"], "csrf": sessao["csrf_token"], "inscritos": inscritos,
        "total": total, "curso": curso, "cursos": CURSOS, "experiencias": EXPERIENCIAS})


@router.post("/inscricoes/{inscricao_id}/remover")
def remover(inscricao_id: int = CaminhoParam(ge=1, le=2**31 - 1), csrf: str = Form(""),
            sessao: dict = Depends(exigir_admin)):
    verificar_csrf(sessao, csrf)
    with db.transacao() as con:
        db.remover_inscricao(con, inscricao_id)
    return RedirectResponse("/admin", status_code=303)


@router.get("/inscricoes.csv")
def exportar_csv(_sessao: dict = Depends(exigir_admin)):
    with db.transacao() as con:
        inscritos = db.listar_inscricoes(con)
    return Response(gerar_csv(inscritos), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="inscritos-minicurso.csv"'})
```

(Se `Response(..., media_type="text/csv")` não acrescentar `charset=utf-8` ao `Content-Type` na versão instalada, use `media_type="text/csv; charset=utf-8"`; o teste só exige o prefixo `text/csv`.)

- [ ] **Step 4: Template completo da lista**

Substituir o conteúdo de `app/templates/admin.html` por:

```html
{% extends "base.html" %}
{% block titulo %}Inscritos{% endblock %}
{% block conteudo %}
<section class="cartao" aria-labelledby="titulo-lista">
  <div class="lista-topo">
    <h2 id="titulo-lista">Inscritos</h2>
    <div class="acoes">
      <a class="botao secundario" href="/admin/inscricoes.csv">Exportar CSV</a>
      <form method="post" action="/admin/logout">
        <input type="hidden" name="csrf" value="{{ csrf }}">
        <button type="submit" class="botao secundario">Sair ({{ usuario }})</button>
      </form>
    </div>
  </div>

  <p class="total" role="status">
    {% if curso %}Mostrando {{ inscritos|length }} de {{ total }} inscritos ({{ curso }})
    {% else %}Total: {{ total }} {{ 'inscrito' if total == 1 else 'inscritos' }}{% endif %}
  </p>

  <form method="get" action="/admin" class="filtro">
    <label for="filtro-curso">Filtrar por curso</label>
    <div class="filtro-linha">
      <select id="filtro-curso" name="curso">
        <option value="">Todos os cursos</option>
        {% for c in cursos %}<option value="{{ c }}"{% if c == curso %} selected{% endif %}>{{ c }}</option>{% endfor %}
      </select>
      <button type="submit" class="botao secundario">Filtrar</button>
    </div>
  </form>

  {% if inscritos %}
  <table>
    <thead>
      <tr><th scope="col">Nome</th><th scope="col">E-mail</th><th scope="col">Curso</th><th scope="col">Período</th><th scope="col">Experiência com IA</th><th scope="col"><span class="so-leitor">Ações</span></th></tr>
    </thead>
    <tbody>
      {% for i in inscritos %}
      <tr>
        <td data-rotulo="Nome">{{ i.nome }}</td>
        <td data-rotulo="E-mail">{{ i.email }}</td>
        <td data-rotulo="Curso">{{ i.curso }}</td>
        <td data-rotulo="Período">{{ i.periodo }}º</td>
        <td data-rotulo="Experiência com IA">{{ experiencias[i.experiencia] }}</td>
        <td>
          <form method="post" action="/admin/inscricoes/{{ i.id }}/remover" data-confirmar="Remover a inscrição de {{ i.nome }}? Esta ação não pode ser desfeita.">
            <input type="hidden" name="csrf" value="{{ csrf }}">
            <button type="submit" class="botao remover" aria-label="Remover inscrição de {{ i.nome }}">Remover</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="vazio">{% if total %}Nenhum inscrito neste curso.{% else %}Nenhuma inscrição ainda.{% endif %}</p>
  {% endif %}
</section>
{% endblock %}
```

- [ ] **Step 5: `admin.js` (confirmação), base e estilos**

Criar `publico/admin.js`:

```js
// A CSP bloqueia onclick inline, então a confirmação é feita aqui.
document.addEventListener('submit', (e) => {
  const msg = e.target.dataset.confirmar;
  if (msg && !confirm(msg)) e.preventDefault();
});
```

Em `app/templates/base.html`, antes de `</body>`, acrescentar: `  <script src="/admin.js"></script>`.

Acrescentar ao final de `publico/style.css`:

```css
.botao { display: inline-flex; align-items: center; justify-content: center; text-decoration: none; }
.acoes { display: flex; flex-wrap: wrap; gap: 8px; }
.filtro-linha { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.filtro-linha select { flex: 1 1 12em; }
```

- [ ] **Step 6: Rodar e ver passar**

Run: `.venv/Scripts/python -m pytest -q`
Expected: tudo verde. Se `test_filtro_hostil_e_ignorado` falhar com `%00` ou 5000 caracteres por causa do cliente HTTP, ajuste só o **valor do parâmetro** (não relaxe a asserção de `200`).

- [ ] **Step 7: Commit**

```bash
git add app publico tests
git commit -m "feat: lista, filtro, remoção com CSRF e CSV na área de admin" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Página pública só envia ao servidor

**Files:**
- Modify (reescrever): `publico/index.html`, `publico/app.js`, `tests/front/teste.js`
- (já movidos na Tarefa 6) `tests/front/teste.html`

**Interfaces:**
- Consumes: `POST /api/inscricoes` (JSON `{nome, email, curso, periodo: number, experiencia, consentimento: true}` → `201 {mensagem}` | `422 {erros}` | `429`).
- Produces (em `app.js`, exportado em `module.exports`): `validar(d) -> {campo: mensagem}`, `traduzirErros(erros: object) -> {campos: object, geral: string}`.

- [ ] **Step 1: Escrever o teste que falha**

Substituir `tests/front/teste.js` por:

```js
// Testes das funções puras de publico/app.js. Dados fictícios apenas.
// Node: `node tests/front/teste.js`  |  Navegador: abrir tests/front/teste.html
const assert = typeof require !== 'undefined' ? require('assert') : { strictEqual: (a, b) => { if (a !== b) throw new Error(`esperado ${JSON.stringify(b)}, veio ${JSON.stringify(a)}`); } };
const A = typeof module !== 'undefined' ? require('../../publico/app.js') : App;

const valido = () => ({ nome: 'Aluno Teste', email: 'teste1@exemplo.com', curso: 'Direito', periodo: '3', experiencia: 'basica', lgpd: true });
const resultados = [];
function teste(nome, fn) {
  try { fn(); resultados.push([true, nome]); } catch (e) { resultados.push([false, `${nome}: ${e.message}`]); }
}
const eq = (a, b) => assert.strictEqual(a, b);
const temErro = (d, campo) => eq(typeof A.validar(d)[campo], 'string');

teste('dados válidos não geram erros', () => eq(Object.keys(A.validar(valido())).length, 0));
teste('nome curto (após trim) é recusado', () => temErro({ ...valido(), nome: ' ab ' }, 'nome'));
teste('nome com mais de 100 caracteres é recusado', () => temErro({ ...valido(), nome: 'x'.repeat(101) }, 'nome'));
teste('e-mail inválido é recusado', () => temErro({ ...valido(), email: 'sem-arroba' }, 'email'));
teste('e-mail com mais de 254 caracteres é recusado', () => temErro({ ...valido(), email: 'a@' + 'b'.repeat(250) + '.co' }, 'email'));
teste('curso fora da lista é recusado', () => temErro({ ...valido(), curso: 'Invalido' }, 'curso'));
teste('período fora de 1 a 10 é recusado', () => {
  temErro({ ...valido(), periodo: '11' }, 'periodo');
  temErro({ ...valido(), periodo: '' }, 'periodo');
});
teste('experiência fora das opções é recusada', () => temErro({ ...valido(), experiencia: 'guru' }, 'experiencia'));
teste('experiência com nome de propriedade do protótipo é recusada', () => {
  for (const x of ['constructor', 'toString', '__proto__', 'hasOwnProperty']) temErro({ ...valido(), experiencia: x }, 'experiencia');
});
teste('experiência em formato de lista é recusada', () => temErro({ ...valido(), experiencia: ['basica'] }, 'experiencia'));
teste('sem consentimento LGPD é recusado', () => temErro({ ...valido(), lgpd: false }, 'lgpd'));

teste('traduzirErros troca consentimento por lgpd', () => {
  const r = A.traduzirErros({ consentimento: 'a', nome: 'b' });
  eq(r.campos.lgpd, 'a');
  eq(r.campos.nome, 'b');
  eq(r.geral, '');
});
teste('traduzirErros separa o erro geral', () => eq(A.traduzirErros({ _geral: 'x' }).geral, 'x'));
teste('traduzirErros com campo desconhecido vira mensagem geral', () => {
  const r = A.traduzirErros({ admin: 'x' });
  eq(Object.keys(r.campos).length, 0);
  eq(typeof r.geral, 'string');
  eq(r.geral.length > 0, true);
});
teste('traduzirErros sem objeto devolve mensagem geral', () => eq(A.traduzirErros(undefined).geral.length > 0, true));

const falhas = resultados.filter(([ok]) => !ok);
resultados.forEach(([ok, msg]) => console.log(`${ok ? 'PASSOU' : 'FALHOU'}  ${msg}`));
console.log(`\n${resultados.length - falhas.length}/${resultados.length} passaram`);
if (typeof document !== 'undefined') {
  document.body.innerHTML = '';
  const pre = document.createElement('pre');
  pre.textContent = resultados.map(([ok, m]) => `${ok ? '✔' : '✘'} ${m}`).join('\n') + `\n\n${resultados.length - falhas.length}/${resultados.length} passaram`;
  document.body.appendChild(pre);
}
if (falhas.length && typeof process !== 'undefined') process.exit(1);
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `node tests/front/teste.js | tail -8`
Expected: falham `traduzirErros` (`A.traduzirErros is not a function`) e os dois testes de tamanho máximo (o `validar` atual ainda não limita 100/254, e ainda pede o argumento `inscritos`, o que também quebra as chamadas com um só argumento).

- [ ] **Step 3: Reescrever `publico/app.js`**

```js
const CURSOS = ['Administração', 'Ciência da Computação', 'Direito', 'Engenharia', 'Medicina', 'Psicologia', 'Design', 'Comunicação', 'Outro'];
const PERIODOS = Array.from({ length: 10 }, (_, i) => String(i + 1));
const EXPERIENCIAS = { nenhuma: 'Nenhuma', basica: 'Básica', avancada: 'Avançada' };
const CAMPOS = ['nome', 'email', 'curso', 'periodo', 'experiencia', 'lgpd'];

// Validação só para feedback rápido. O servidor valida de novo e é quem decide.
function validar(d) {
  const erros = {};
  const nome = String(d.nome || '').trim();
  const email = String(d.email || '').trim();
  if (nome.length < 3 || nome.length > 100) erros.nome = 'Informe seu nome completo (3 a 100 caracteres).';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254) erros.email = 'Informe um e-mail válido, como nome@exemplo.com.';
  if (!CURSOS.includes(d.curso)) erros.curso = 'Selecione seu curso.';
  if (!PERIODOS.includes(String(d.periodo))) erros.periodo = 'Selecione seu período (1º a 10º).';
  if (typeof d.experiencia !== 'string' || !Object.hasOwn(EXPERIENCIAS, d.experiencia)) erros.experiencia = 'Escolha seu nível de experiência com IA.';
  if (d.lgpd !== true) erros.lgpd = 'É necessário consentir com o uso dos dados para se inscrever.';
  return erros;
}

// Converte { campo: mensagem } do servidor para os nomes dos campos desta página.
function traduzirErros(erros) {
  const campos = {};
  let geral = '';
  if (erros && typeof erros === 'object') {
    for (const [campo, msg] of Object.entries(erros)) {
      const nome = campo === 'consentimento' ? 'lgpd' : campo;
      if (CAMPOS.includes(nome)) campos[nome] = String(msg);
      else if (campo === '_geral') geral = String(msg);
    }
  }
  if (!Object.keys(campos).length && !geral) geral = 'Não foi possível validar os dados. Revise o formulário.';
  return { campos, geral };
}

const App = { validar, traduzirErros };
if (typeof module !== 'undefined') module.exports = App;

if (typeof document !== 'undefined' && document.getElementById('form')) {
  const $ = (id) => document.getElementById(id);
  const form = $('form');

  function avisar(texto) { $('aviso').textContent = texto; $('aviso').hidden = !texto; }

  function lerDados() {
    const f = new FormData(form);
    return { nome: f.get('nome') || '', email: f.get('email') || '', curso: f.get('curso') || '',
      periodo: f.get('periodo') || '', experiencia: f.get('experiencia') || '', lgpd: f.get('lgpd') === 'on' };
  }

  // Elemento que recebe aria-invalid e o link do resumo de erros.
  const alvo = (campo) => (campo === 'experiencia' ? $('grupo-experiencia') : $(campo));
  const alvoFoco = (campo) => (campo === 'experiencia' ? $('exp-nenhuma') : $(campo));

  function mostrarErro(campo, msg) {
    $(`erro-${campo}`).textContent = msg || '';
    if (msg) alvo(campo).setAttribute('aria-invalid', 'true'); else alvo(campo).removeAttribute('aria-invalid');
  }

  function limparErros() { CAMPOS.forEach((c) => mostrarErro(c, '')); $('resumo').hidden = true; avisar(''); }

  function mostrarErros(erros) {
    const lista = $('resumo-lista');
    lista.replaceChildren();
    for (const [campo, msg] of Object.entries(erros)) {
      mostrarErro(campo, msg);
      const a = document.createElement('a');
      a.href = `#${alvoFoco(campo).id}`;
      a.textContent = msg;
      const li = document.createElement('li');
      li.appendChild(a);
      lista.appendChild(li);
    }
    $('resumo').hidden = false;
    $('resumo').focus();
  }

  // Valida um campo só (blur/input), sem tocar nos outros.
  function validarCampo(campo) { mostrarErro(campo, validar(lerDados())[campo]); }

  CURSOS.forEach((c) => $('curso').add(new Option(c, c)));
  PERIODOS.forEach((p) => $('periodo').add(new Option(`${p}º`, p)));

  form.addEventListener('focusout', (e) => {
    const campo = e.target.name;
    if (!CAMPOS.includes(campo)) return;
    // Campo vazio só acusa erro no envio (ou se já estava inválido); rádio e checkbox idem.
    const preenchido = ['nome', 'email', 'curso', 'periodo'].includes(campo) && e.target.value !== '';
    if (preenchido || alvo(campo).getAttribute('aria-invalid')) validarCampo(campo);
  });
  form.addEventListener('input', (e) => {
    const campo = e.target.name;
    if (CAMPOS.includes(campo) && alvo(campo).getAttribute('aria-invalid')) validarCampo(campo);
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    $('sucesso').hidden = true;
    const dados = lerDados();
    const erros = validar(dados);
    limparErros();
    if (Object.keys(erros).length) { mostrarErros(erros); return; }

    const botao = form.querySelector('button[type="submit"]');
    botao.disabled = true;
    try {
      const r = await fetch('/api/inscricoes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nome: dados.nome.trim(), email: dados.email.trim(), curso: dados.curso,
          periodo: Number(dados.periodo), experiencia: dados.experiencia, consentimento: true }),
      });
      if (r.status === 201) {
        form.reset();
        $('sucesso').textContent = (await r.json()).mensagem;
        $('sucesso').hidden = false;
      } else if (r.status === 422) {
        const { campos, geral } = traduzirErros((await r.json()).erros);
        if (Object.keys(campos).length) mostrarErros(campos);
        if (geral) avisar(geral);
      } else if (r.status === 429) {
        avisar('Muitas tentativas. Aguarde um instante e tente de novo.');
      } else {
        avisar('Não foi possível enviar sua inscrição. Tente novamente mais tarde.');
      }
    } catch (err) {
      avisar('Sem conexão com o servidor. Verifique a internet e tente novamente.');
    } finally {
      botao.disabled = false;
    }
  });
}
```

- [ ] **Step 4: Reescrever `publico/index.html`**

```html
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Inscrição — Claude AI: o Ecossistema da Anthropic</title>
  <meta name="description" content="Inscrição para o minicurso Claude AI: o Ecossistema da Anthropic.">
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header class="topo">
    <h1>Claude AI: o Ecossistema da Anthropic</h1>
    <p>Minicurso para alunos da universidade. Preencha o formulário para garantir sua vaga.</p>
  </header>

  <main>
    <section class="cartao" aria-labelledby="titulo-form">
      <h2 id="titulo-form">Inscrição</h2>

      <p id="sucesso" class="sucesso" role="status" aria-live="polite" hidden></p>
      <p id="aviso" class="erro" role="alert" hidden></p>

      <div id="resumo" class="resumo" role="alert" tabindex="-1" hidden>
        <h3>Revise os campos abaixo</h3>
        <ul id="resumo-lista"></ul>
      </div>

      <form id="form" novalidate>
        <div class="campo">
          <label for="nome">Nome completo</label>
          <input id="nome" name="nome" type="text" autocomplete="name" required maxlength="100" aria-describedby="erro-nome">
          <p id="erro-nome" class="erro"></p>
        </div>

        <div class="campo">
          <label for="email">E-mail</label>
          <input id="email" name="email" type="email" autocomplete="email" required maxlength="254" aria-describedby="erro-email">
          <p id="erro-email" class="erro"></p>
        </div>

        <div class="linha">
          <div class="campo">
            <label for="curso">Curso</label>
            <select id="curso" name="curso" required aria-describedby="erro-curso">
              <option value="">Selecione…</option>
            </select>
            <p id="erro-curso" class="erro"></p>
          </div>

          <div class="campo">
            <label for="periodo">Período</label>
            <select id="periodo" name="periodo" required aria-describedby="erro-periodo">
              <option value="">Selecione…</option>
            </select>
            <p id="erro-periodo" class="erro"></p>
          </div>
        </div>

        <fieldset class="campo" id="grupo-experiencia" aria-describedby="erro-experiencia">
          <legend>Experiência com IA</legend>
          <div class="opcoes">
            <label class="opcao"><input type="radio" id="exp-nenhuma" name="experiencia" value="nenhuma"> Nenhuma</label>
            <label class="opcao"><input type="radio" id="exp-basica" name="experiencia" value="basica"> Básica</label>
            <label class="opcao"><input type="radio" id="exp-avancada" name="experiencia" value="avancada"> Avançada</label>
          </div>
          <p id="erro-experiencia" class="erro"></p>
        </fieldset>

        <div class="campo">
          <label class="opcao consentimento">
            <input type="checkbox" id="lgpd" name="lgpd" required aria-describedby="erro-lgpd">
            <span>Autorizo o uso do meu nome, e-mail, curso, período e experiência apenas para a organização do minicurso (LGPD). Os dados ficam guardados no servidor do evento e só a organização tem acesso.</span>
          </label>
          <p id="erro-lgpd" class="erro"></p>
        </div>

        <button type="submit" class="botao">Inscrever-se</button>
      </form>
    </section>
  </main>

  <script src="app.js"></script>
</body>
</html>
```

(O texto do consentimento mudou: antes dizia que os dados ficavam só no navegador. `VERSAO_CONSENTIMENTO` em `app/validacao.py` continua `2026-10-01`, a data desta versão do texto.)

- [ ] **Step 5: Rodar e ver passar**

Run: `node tests/front/teste.js | tail -2` → Expected: `15/15 passaram`.
Run: `.venv/Scripts/python -m pytest -q` → Expected: tudo verde (inclui `test_pagina_publica_e_servida`).

- [ ] **Step 6: Commit**

```bash
git add publico tests/front
git commit -m "feat: página pública só envia a inscrição ao servidor" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: README, verificação ponta a ponta e fechamento

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: tudo das tarefas anteriores.

- [ ] **Step 1: Escrever o README**

Criar `README.md`:

````markdown
# Minicurso "Claude AI: o Ecossistema da Anthropic" — inscrição

Demo de aula: FastAPI + SQLite. A página pública só envia a inscrição; a lista e o CSV ficam numa área de admin com login.

## Rodar

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # Linux/macOS: .venv/bin/python
.venv/Scripts/python criar_admin.py                            # pede usuário e senha (mín. 12 caracteres)
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1
```

- Página pública: http://127.0.0.1:8000/
- Admin: http://127.0.0.1:8000/admin/login

Configuração (variáveis de ambiente): `DATABASE_PATH` (padrão `inscricoes.db`) e `COOKIE_SECURE=1` (ligar quando houver HTTPS).

## Testes

```bash
.venv/Scripts/python -m pytest        # servidor
node tests/front/teste.js             # JS da página pública
```

## Segurança

As decisões e o motivo de cada uma estão em `docs/superpowers/specs/2026-10-01-backend-admin-design.md` (seção "Segurança: decisões e por quê"); no código, os comentários "Decisão N" apontam para a linha correspondente.
````

- [ ] **Step 2: Suíte completa**

Run: `.venv/Scripts/python -m pytest -q` → Expected: tudo verde, sem avisos de erro.
Run: `node tests/front/teste.js | tail -1` → Expected: `15/15 passaram`.

- [ ] **Step 3: Verificação ponta a ponta no navegador (banco temporário)**

Subir o servidor com um banco descartável e criar um admin de teste por script (sem prompt), sem tocar em dados reais:

```bash
export DATABASE_PATH="$(mktemp -d)/e2e.db"
.venv/Scripts/python -c "from app import db, seguranca; db.iniciar(); con = db.conectar(); seguranca.criar_admin(con, 'admin', 'senha-de-teste-123'); con.commit()"
.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
(O último comando em segundo plano.) Com as ferramentas de navegador, em `http://127.0.0.1:8000/`:

1. Enviar o formulário vazio: aparece o resumo de erros com foco.
2. Enviar uma inscrição fictícia válida: mensagem "Recebemos sua inscrição. Obrigado!". Enviar a mesma de novo: mesma mensagem.
3. Confirmar que a página pública **não** mostra lista nenhuma e que `GET /admin` sem login redireciona para `/admin/login`.
4. Entrar em `/admin/login`: ver a lista com 1 inscrito (não 2), total, filtro por curso e botão Remover. Abrir `/admin/inscricoes.csv` já logado e conferir que baixa; sem login responde 401.
5. Sair (logout) e confirmar que `/admin` volta a redirecionar.

Parar o servidor ao terminar e apagar o banco temporário.

- [ ] **Step 4: Commit final**

```bash
git add README.md
git commit -m "docs: README com execução, testes e referência de segurança" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git status --short
```
Expected: árvore limpa.

---

## Self-Review

**1. Cobertura da spec**
- Estrutura e dependências → Tarefas 1 e 10. Tabelas (`inscricoes`, `admins`, `sessoes`, `tentativas_login`) e `versao_consentimento` → Tarefa 1.
- Validação no servidor (limites, `Literal`, regex, consentimento) → Tarefa 2; resposta `422` por campo em pt-BR sem ecoar valor → Tarefa 6.
- Fluxo de inscrição (201 neutro, duplicado sem gravar, 429) → Tarefa 6. Login/logout → Tarefa 7. Lista, filtro no servidor, remover com CSRF e `confirm()` externo, CSV só admin → Tarefa 8. `criar_admin.py` (senha dupla, mínimo 12, usuário repetido) → Tarefa 3.
- Segurança 1 (Argon2id, rehash) → T3/T7; 2 (mensagem única, hash falso) → T3/T7; 3 (5 falhas/15 min) → T4/T7; 4 (token, SHA-256, 2 h, token novo, logout, limpeza) → T3/T7; 5 (cookie) → T7; 6 (CSRF) → T3/T7/T8; 7 (deny by default no router, 401/redirect) → T7 (com teste de enumeração de rotas); 8 (`no-store`) → T6/T8; 9 (CSP etc.) → T6; 10 (Pydantic, SQL parametrizado, limite por IP) → T2/T4/T6; 11 (só `publico/`, docs desligados, debug off, sem senha em arquivo) → T6; 12 (logs sem dados pessoais) → teste de log na T7 (não há log de aplicação; `uvicorn` registra só caminho).
- Front público (perde lista/filtro/remoção/CSV/`localStorage`, `admin.js`, `teste.js` só com `validar`) → T8/T9.
- Testes listados na spec: validação, duplicado, SQL injection, rotas protegidas, CSRF, login/sessão, cookie/cabeçalhos, banco sem senha, CSV, XSS, limite, `criar_admin` → todos têm teste (T1–T9).
- Lacuna conhecida e aceita: o erro `500` genérico não tem teste dedicado (depende do comportamento padrão do Starlette com `debug` desligado).

**2. Placeholders:** nenhum "TBD/TODO"; todos os passos de código trazem o código. A única condicional é o ajuste de `Response(..., media_type)` na T8, com instrução exata.

**3. Consistência de tipos/nomes:** `criar_sessao -> (token, csrf)` (T3) é usado assim na T7; `obter_sessao -> dict` com `admin_id/csrf_token/usuario` (T3) é o que `exigir_admin` devolve e os handlers leem; `normalizar_usuario/registrar_falha/bloqueado/limpar_falhas` (T4) coincidem com o uso na T7; `ip_do_cliente` vem de `rotas_publicas` (T6) e é importado na T7; `gerar_csv` (T5) recebe `Row` ou `dict` (T8 passa `Row`); `MENSAGENS_ERRO` (T2) é usada na T6; `validar/traduzirErros` (T9) batem entre `app.js` e `teste.js`; chaves do JSON `consentimento` (servidor) ↔ `lgpd` (formulário) tratadas em `traduzirErros`.

**4. Review Focus:** as 5 entradas têm teste: (1) corpo/tipos hostis → `test_corpo_ilegivel_devolve_422_e_nao_500` e `test_tipos_errados_devolvem_422` (T6); (2) CSV hostil → `test_conteudo_hostil_reabre_identico` e afins (T5); (3) cookie/CSRF adulterados → T3 (`test_token_hostil…`, `test_csrf_nao_ascii…`), T7 (`test_cookie_adulterado…`, `test_logout_sem_csrf_valido…`), T8 (`test_remover_sem_csrf_valido…`); (4) filtro/id → `test_filtro_hostil_e_ignorado`, `test_remover_id_fora_do_intervalo_e_422` (T8); (5) e-mail duplicado com variações → `test_email_repetido_com_outra_grafia_nao_duplica` (T1) e `test_duplicado_responde_igual…` (T6).
