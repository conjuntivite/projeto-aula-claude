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
