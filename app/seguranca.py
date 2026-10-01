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
