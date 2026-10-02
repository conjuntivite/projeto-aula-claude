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

- Abaixo do formulário, com o total ("Total: N inscritos").
- Filtro por curso: com um curso escolhido, mostra "Mostrando X de N inscritos (Curso)". O CSV exporta sempre todos os inscritos.
- Mostra todos os campos (nome, e-mail, curso, período, experiência).
- Botão "Remover" por inscrito, com `confirm()` nativo antes. Depois de remover, o foco vai para o total. O e-mail removido pode ser inscrito de novo.
- Sem edição.
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

Referência de design: skill `ui-ux-pro-max` (só guia; o código segue em HTML/CSS/JS puros, sem Tailwind, shadcn nem fontes externas). Estilo: Minimalismo, claro, sem tema escuro. Dials: variância 2, movimento 2, densidade 4.

**Tokens** (variáveis CSS em `:root`; paleta "warm terracotta" da skill):

| Token | Valor | Uso |
|---|---|---|
| `--cor-primaria` | `#9A3412` | botões, links, foco (`--ring`) |
| `--cor-sobre-primaria` | `#FFFFFF` | texto sobre a primária |
| `--cor-fundo` | `#FFFBEB` | fundo da página |
| `--cor-cartao` | `#FFFFFF` | formulário e lista |
| `--cor-texto` | `#0F172A` | texto principal |
| `--cor-texto-suave` | `#475569` | ajuda, rótulos secundários |
| `--cor-suave` | `#F8F2F0` | linhas alternadas, estado vazio |
| `--cor-borda` | `#F2E6E2` | bordas de cartão e tabela |
| `--cor-erro` | `#DC2626` | erros (texto e borda) |
| `--cor-sucesso` | `#047857` | mensagem de sucesso. A paleta sugere `#059669`; usamos um tom mais escuro para manter contraste 4.5:1 em texto |

**Tipografia:** pilha do sistema (`system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`), pois todas as fontes sugeridas pela skill vêm do Google Fonts (dependência externa). Corpo 16px, `line-height` 1.5, títulos com peso 700.

**Layout e componentes:**
- CSS com variáveis, grid e media query, mobile-first.
- Celular (a partir de 360px): uma coluna, alvos de toque de no mínimo 44px, lista em cards.
- Tela larga (breakpoint ~768px): formulário com largura limitada, lista em tabela.
- Sem emojis como ícones; se houver ícone, SVG inline.
- Transições de 150-250ms só em `color`, `background` e `border-color`. Respeitar `prefers-reduced-motion`.
- `cursor: pointer` nos elementos clicáveis; botão desabilitado com aparência distinta.
- Checagem final de responsividade em 375, 768, 1024 e 1440px.

## Acessibilidade e feedback de formulário

- Labels visíveis e associados a cada campo (nunca placeholder como label); `fieldset`/`legend` no grupo de rádio.
- Erro inline abaixo de cada campo inválido, ligado ao campo por `aria-describedby`, com `aria-invalid`. Validação no `blur` e, depois do primeiro erro, também no `input`.
- Resumo de erros no topo do formulário após um envio inválido: `role="alert"`, `tabindex="-1"`, foco movido para ele, cada item com link para o campo. Os erros inline permanecem.
- Sucesso em região `aria-live="polite"`.
- Foco visível (anel com `--cor-primaria`), nunca removido.
- Contraste mínimo 4.5:1 para texto; erro e estado nunca dependem só de cor (texto de erro sempre presente).

## Estrutura do `app.js`

Funções simples, sem classes:

- Puras (testáveis): `validar(dados, inscritos)`, `emailDuplicado`, `gerarCsv(inscritos)`, `escaparCsv(valor)`.
- Efeitos: `carregar()`, `salvar(lista)`, `renderizar(lista)`, `exportarCsv()`, handler do `submit`.

## Testes

- Somente dados fictícios (ex.: `Aluno Teste`, `teste1@exemplo.com`).
- `teste.html` cobre: validação de cada campo, duplicado (maiúsculas/minúsculas), escape de CSV, neutralização de fórmula, BOM e separador.
- Verificação manual: fluxo completo no navegador, a 360px e a 1280px, e abrir o CSV no Excel.

## Fora de escopo (YAGNI)

Login, backend, edição de inscritos, paginação, busca, política de privacidade formal, tema escuro, bibliotecas externas.
