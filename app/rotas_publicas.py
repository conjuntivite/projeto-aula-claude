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
