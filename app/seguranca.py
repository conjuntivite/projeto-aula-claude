import hashlib
import hmac
import secrets
import sqlite3
import time
from collections import defaultdict, deque

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
    except (VerificationError, InvalidHashError, UnicodeError, TypeError, AttributeError):
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
    con.execute("DELETE FROM tentativas_login WHERE criada_em <= ?", (db.agora_mais(-JANELA_LOGIN_S),))


# Decisão 6: comparação em tempo constante. Codifica antes porque compare_digest
# lança TypeError com texto não ASCII.
def csrf_valido(esperado: str, recebido: str | None) -> bool:
    if not recebido:
        return False
    return hmac.compare_digest(esperado.encode("utf-8", "replace"), recebido.encode("utf-8", "replace"))


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
