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
