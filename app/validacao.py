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
