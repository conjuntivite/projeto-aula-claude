# Página de inscrição — minicurso "Claude AI: o Ecossistema da Anthropic"

Data: 2026-10-01

## Objetivo

Página estática de inscrição para o minicurso, para alunos da universidade. Serve como **demo de aula**: ninguém coleta inscrições reais por ela. Idioma: pt-BR. Sem login, sem backend, sem bibliotecas externas.

## Entregáveis

- `index.html`, `style.css`, `app.js` (JS puro, sem módulos ES, para funcionar via `file://`).
- `teste.html` (opcional): roda `assert` sobre as funções puras de validação e CSV. Sem framework de testes.

## Formulário

| Campo | Tipo | Regra |
|---|---|---|
| Nome | texto | obrigatório, mínimo 3 caracteres após `trim` |
| E-mail | `type=email` | obrigatório, formato válido, único (sem diferenciar maiúsculas) |
| Curso | select | obrigatório; lista fixa de cerca de 8 cursos comuns mais "Outro" |
| Período | select | obrigatório; 1º a 10º |
| Experiência com IA | rádio | obrigatório; nenhuma, básica, avançada |
| Consentimento LGPD | checkbox | obrigatório; texto curto de consentimento (demo, sem política formal) |

- Validação com atributos nativos (`required`, `type=email`, `minlength`) e Constraint Validation API, com mensagens em pt-BR.
- E-mail duplicado é recusado com mensagem de erro no campo.
- Sucesso: mensagem em região `aria-live`, formulário limpo, lista atualizada.

## Lista de inscritos

- Abaixo do formulário, com contador.
- Mostra todos os campos (nome, e-mail, curso, período, experiência).
- Sem edição e sem remoção.
- Estado vazio: texto "Nenhuma inscrição ainda".
- Renderização com `textContent`, nunca `innerHTML` (evita XSS).

## Persistência

- `localStorage`, chave única, array JSON de objetos.
- Se o `localStorage` estiver indisponível ou o JSON estiver corrompido: começa com lista vazia e avisa o usuário.

## Exportar CSV

- Botão "Exportar CSV", desabilitado com a lista vazia.
- Separador `;`, BOM UTF-8 (`﻿`), quebra de linha `\r\n`.
- Cabeçalho em pt-BR.
- Escapa aspas duplas e campos com `;`, aspas ou quebra de linha.
- Neutraliza injeção de fórmula: células que começam com `=`, `+`, `-` ou `@` recebem apóstrofo na frente.
- Download via `Blob` + `<a download>`.

## Visual e layout

- Claro, minimalista, tons quentes: fundo off-white, acento terracota, fonte do sistema. Sem logos ou marcas.
- CSS com variáveis, grid e media query.
- Celular: uma coluna, lista em cards.
- Tela larga: formulário com largura limitada, lista em tabela.

## Acessibilidade

- Labels associados a cada campo, `fieldset`/`legend` no grupo de rádio.
- Erros e sucesso em `aria-live`.
- Foco visível e contraste adequado.

## Estrutura do `app.js`

Funções simples, sem classes:

- Puras (testáveis): `validar(dados, inscritos)`, `emailDuplicado`, `gerarCsv(inscritos)`, `escaparCsv(valor)`.
- Efeitos: `carregar()`, `salvar(lista)`, `renderizar(lista)`, `exportarCsv()`, handler do `submit`.

## Testes

- Somente dados fictícios (ex.: `Aluno Teste`, `teste1@exemplo.com`).
- `teste.html` cobre: validação de cada campo, duplicado (maiúsculas/minúsculas), escape de CSV, neutralização de fórmula, BOM e separador.
- Verificação manual: fluxo completo no navegador, a 360px e a 1280px, e abrir o CSV no Excel.

## Fora de escopo (YAGNI)

Login, backend, edição ou remoção de inscritos, paginação, busca, política de privacidade formal, tema escuro, bibliotecas externas.
