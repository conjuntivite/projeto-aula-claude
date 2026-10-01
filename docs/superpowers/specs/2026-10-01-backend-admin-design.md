# Backend de inscrição com área de admin — FastAPI + SQLite

Data: 2026-10-01
Evolui: `2026-10-01-inscricao-minicurso-design.md` (página só de front-end com `localStorage`).

## Objetivo

Transformar a página de inscrição num sistema com backend. A página pública **só envia** a inscrição ao servidor e não mostra a lista. Uma área de admin, com login, senha com hash e sessão, é o único lugar onde se vê a lista, se filtra, se remove e se exporta o CSV.

## Decisões acordadas

| Tema | Decisão |
|---|---|
| Ambiente | Só local, demo de aula (`127.0.0.1`). Itens que dependem de HTTPS ficam configuráveis. |
| Primeiro admin | `criar_admin.py` pede usuário e senha no terminal. Nenhuma senha em código, arquivo ou variável de ambiente. |
| Escopo do admin | Total, filtro por curso, remover com confirmação, exportar CSV. Sem trocar senha e sem múltiplos admins pela interface. |
| Telas do admin | HTML gerado no servidor com Jinja2 (autoescape ligado). |
| Sessão | No servidor (SQLite). O cookie guarda só um token aleatório. |
| Hash de senha | Argon2id (`argon2-cffi`). |
| E-mail duplicado | A página pública responde sucesso neutro e não grava de novo. |
| Abordagem | Um único app FastAPI serve página pública, API e `/admin` na mesma origem. Sem CORS, sem ORM. |

## Estrutura

```
app/
  main.py            # cria o app, monta rotas, cabeçalhos de segurança, exceções
  config.py          # DATABASE_PATH, COOKIE_SECURE
  db.py              # sqlite3, schema, consultas parametrizadas
  seguranca.py       # Argon2id, token de sessão, CSRF, limite de tentativas
  validacao.py       # modelo Pydantic da inscrição, CURSOS, lista de experiências
  csv_export.py      # geração do CSV (porta de escaparCsv/gerarCsv)
  rotas_publicas.py  # POST /api/inscricoes
  rotas_admin.py     # /admin/*
  templates/         # base.html, login.html, admin.html (Jinja2)
publico/             # index.html, style.css, app.js, admin.js (estáticos)
criar_admin.py
requirements.txt
tests/
```

Dependências: `fastapi`, `uvicorn`, `jinja2`, `python-multipart`, `argon2-cffi`. Para testes: `pytest`, `httpx`. O `sqlite3` é da biblioteca padrão. Execução: `uvicorn app.main:app --host 127.0.0.1`.

## Dados

Conexão por requisição, `PRAGMA foreign_keys=ON`, `CREATE TABLE IF NOT EXISTS` ao iniciar. O arquivo `.db` fica fora de `publico/` e no `.gitignore`.

| Tabela | Campos |
|---|---|
| `inscricoes` | `id`, `nome`, `email`, `email_normalizado` (UNIQUE: `strip().lower()`), `curso`, `periodo` (inteiro 1–10), `experiencia`, `consentimento_em` (ISO UTC), `versao_consentimento`, `criado_em` |
| `admins` | `id`, `usuario` (UNIQUE), `senha_hash`, `criado_em` |
| `sessoes` | `token_hash` (chave, SHA-256 do token), `admin_id` (FK, `ON DELETE CASCADE`), `csrf_token`, `criada_em`, `expira_em` |
| `tentativas_login` | `usuario`, `ip`, `criada_em` |

`versao_consentimento` registra qual texto o aluno aceitou (constante no código, atualizada se o texto mudar).

## Validação da inscrição (servidor é a fonte da verdade)

Modelo Pydantic, mesmas regras do `validar()` atual mais limites:
- `nome`: `strip`, 3 a 100 caracteres.
- `email`: regex `^[^\s@]+@[^\s@]+\.[^\s@]+$` e no máximo 254 caracteres (sem `email-validator`, para não somar dependência).
- `curso`: um dos `CURSOS`. `periodo`: 1 a 10. `experiencia`: `nenhuma`, `basica` ou `avancada` (tipo `Literal`).
- `consentimento`: tem de ser `true`.

A validação do navegador (`app.js`) continua só para feedback rápido; nunca é confiada.

## Fluxos

- **Inscrição:** `app.js` envia `POST /api/inscricoes` (JSON).
  - Inválido: `422` com erros por campo; a tela mostra inline como hoje.
  - Válido ou e-mail repetido: `201` com a mesma mensagem. No repetido, nada é gravado (checagem prévia mais captura de `IntegrityError` na UNIQUE, para a condição de corrida).
  - Excesso de envios: `429`.
- **Login:** `GET /admin/login` (formulário) e `POST /admin/login`. Com sucesso: cria sessão, define cookie, `303` para `/admin`. Logout: `POST /admin/logout` com CSRF.
- **Lista:** `GET /admin?curso=…`. O filtro é aplicado no servidor e só aceita valores de `CURSOS`. Mostra total (ou "Mostrando X de N") e tabela.
- **Remover:** `POST /admin/inscricoes/{id}/remover` com CSRF. Id inexistente apenas redireciona. A confirmação vem do `admin.js` externo (a CSP bloqueia `onclick` inline), que pede `confirm()` nos formulários marcados com `data-confirmar`.
- **CSV:** `GET /admin/inscricoes.csv`. Separador `;`, BOM UTF-8, `\r\n`, mesmo cabeçalho de hoje, neutralização de fórmulas (`= + - @`, tab e `\r` iniciais). Exporta sempre todos os inscritos.
- **`criar_admin.py`:** `getpass`, senha pedida duas vezes, mínimo 12 caracteres, recusa usuário já existente.

## Segurança: decisões e por quê

| # | Decisão | Ameaça que evita |
|---|---|---|
| 1 | Senha com Argon2id (`PasswordHasher`, sal aleatório embutido, `check_needs_rehash` no login) | Vazamento do banco revelar senhas; tentativa em massa (o hash é lento de propósito). |
| 2 | Login com mensagem única ("Usuário ou senha inválidos"); usuário inexistente também executa um hash falso | Enumeração de usuários por texto ou por tempo de resposta. |
| 3 | Limite de tentativas: 5 falhas por usuário e IP em 15 min bloqueiam temporariamente (`tentativas_login`), com a mesma mensagem para qualquer nome de usuário | Força bruta de senha, sem vazar se o usuário existe. |
| 4 | Token de sessão `secrets.token_urlsafe(32)`; o banco guarda só o SHA-256; expira em 2 h; novo token a cada login; logout apaga a linha; sessões expiradas são removidas a cada login | Quem lê o banco não usa as sessões; *session fixation*; logout que não invalida. |
| 5 | Cookie `sessao`: `HttpOnly`, `SameSite=Strict`, `Path=/admin`, `Secure` conforme `COOKIE_SECURE` (desligado em `http://localhost`, obrigatório com HTTPS) | Roubo do cookie por XSS; envio por outros sites; vazamento em HTTP. |
| 6 | CSRF: token por sessão em campo oculto nos POSTs do admin, comparado com `secrets.compare_digest` | Outro site induzir o admin a remover inscritos (defesa em camadas com `SameSite`). O formulário de login não tem token: o `SameSite=Strict` cobre o risco restante. |
| 7 | Autorização negada por padrão: a dependência `exigir_admin` fica no router inteiro de `/admin`, incluindo o CSV. Sem sessão válida: redireciona ao login (HTML) ou responde 401 | Esquecer de proteger uma rota nova. |
| 8 | `Cache-Control: no-store` em páginas do admin e no CSV | Dados pessoais em cache do navegador ou de proxy. |
| 9 | Cabeçalhos globais: CSP `default-src 'self'; frame-ancestors 'none'; form-action 'self'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` | XSS, clickjacking, vazamento de URL. |
| 10 | Inscrição pública: validação Pydantic com limites, `INSERT` parametrizado, resposta neutra para duplicado, limite de 10 envios por minuto por IP (`request.client.host`; `X-Forwarded-For` não é confiado) | Entrada inválida, SQL injection, enumeração de e-mails, abuso e lotação do banco. |
| 11 | Superfície mínima: só `publico/` é estático (montado depois das rotas para não encobri-las), `/docs`, `/redoc` e `/openapi.json` desligados, `debug` desligado, nenhuma senha em arquivo | Banco e descrição da API expostos; vazamento de pilha de erro. |
| 12 | Logs sem senha, e-mail ou nome | Dados pessoais em logs. |

Limite conhecido: o limite de envios por IP da inscrição pública fica em memória (zera ao reiniciar e não é compartilhado entre processos). Suficiente para a demo; em produção, trocar por armazenamento compartilhado.

## Front-end público

- `index.html`: perde a seção da lista. `app.js`: perde lista, filtro, remoção, CSV e `localStorage`; envia por `fetch` e mostra erros do servidor inline. `teste.js`: fica só com os testes do `validar`.
- `admin.js`: só o `confirm()` dos formulários marcados.
- Dados antigos do `localStorage` são descartados (demo).

## Erros e operação

- Erro `500` genérico, sem pilha.
- Id inexistente em remoção: redireciona.
- `COOKIE_SECURE` e `DATABASE_PATH` são as únicas configurações.

## Testes

`pytest` com `TestClient` e banco temporário. Dados fictícios.

- **Validação:** a bateria do `validar()` atual portada para o Pydantic, mais os limites de tamanho e o prototype keys (`constructor`, `toString`…).
- **Duplicado:** resposta neutra e uma única linha gravada, inclusive com maiúsculas diferentes.
- **SQL injection:** a string maliciosa é gravada como texto literal.
- **Rotas protegidas:** sem sessão, `/admin`, a remoção e o CSV devolvem 401 ou redirecionam.
- **CSRF:** POST sem token ou com token errado é recusado.
- **Login e sessão:** mensagem igual para usuário errado e senha errada; bloqueio após 5 falhas; logout invalida o token; sessão expirada é recusada; novo token a cada login.
- **Cookie e cabeçalhos:** cookie com `HttpOnly` e `SameSite=Strict`, `Secure` conforme config; CSP, `nosniff` e `no-store` presentes; `/docs` devolve 404.
- **Banco:** senha nunca em texto no banco nem no log; só o hash do token é guardado.
- **CSV:** `=1+1` e `\t=1+1` saem com apóstrofo; separador, BOM e cabeçalho corretos; só admin acessa.
- **XSS:** nome `<script>` aparece escapado na lista.
- **Limite de envios:** o 11º envio no mesmo minuto recebe `429`.
- **`criar_admin.py`:** recusa senha curta e usuário repetido.

## Fora de escopo (YAGNI)

Múltiplos admins e troca de senha pela interface, recuperação de senha, 2FA, ORM e migrações, CORS, terminação HTTPS e deploy, paginação e busca, e-mail de confirmação ao aluno.
