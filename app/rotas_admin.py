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
