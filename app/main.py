from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.rotas_admin import NaoAutenticado, login_router
from app.rotas_admin import router as rotas_admin
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
        campo = loc[1] if len(loc) > 1 and loc[1] in MENSAGENS_ERRO else "_geral"
        erros[campo] = MENSAGENS_ERRO.get(campo, "Valor inválido.")
    return JSONResponse({"erros": erros}, status_code=422)


async def nao_autenticado(request: Request, _exc: NaoAutenticado):
    # Decisão 7: páginas HTML vão para o login; POST e CSV recebem 401.
    if request.method == "GET" and not request.url.path.endswith(".csv"):
        return RedirectResponse("/admin/login", status_code=303)
    return JSONResponse({"detail": "Não autenticado."}, status_code=401)


def criar_app() -> FastAPI:
    # Decisão 11: documentação da API desligada; debug desligado (erro 500 genérico).
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.limitador = LimitadorPorIp(maximo=10, janela_s=60)
    app.middleware("http")(cabecalhos)
    app.add_exception_handler(RequestValidationError, erro_validacao)
    app.add_exception_handler(NaoAutenticado, nao_autenticado)
    app.include_router(rotas_publicas)
    # FastAPI >= 0.142 inclui routers de forma preguiçosa (app.routes não lista os caminhos).
    # Anexamos as rotas já resolvidas (prefixo e dependências do router vêm junto) para que
    # o teste de "toda rota do admin exige sessão" consiga enumerá-las.
    app.router.routes.extend(login_router.routes)
    app.router.routes.extend(rotas_admin.routes)
    # Decisão 11: só publico/ é servido. Montado por último para não encobrir as rotas.
    app.mount("/", StaticFiles(directory=PUBLICO, html=True), name="publico")
    return app


app = criar_app()
