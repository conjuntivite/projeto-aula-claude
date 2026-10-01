// Testes das funções puras de app.js. Dados fictícios apenas.
// Node: `node teste.js`  |  Navegador: abrir teste.html
const assert = typeof require !== 'undefined' ? require('assert') : { strictEqual: (a, b) => { if (a !== b) throw new Error(`esperado ${JSON.stringify(b)}, veio ${JSON.stringify(a)}`); } };
const A = typeof module !== 'undefined' ? require('../../publico/app.js') : App;

const valido = () => ({ nome: 'Aluno Teste', email: 'teste1@exemplo.com', curso: 'Direito', periodo: '3', experiencia: 'basica', lgpd: true });
const resultados = [];
function teste(nome, fn) {
  try { fn(); resultados.push([true, nome]); } catch (e) { resultados.push([false, `${nome}: ${e.message}`]); }
}
const eq = (a, b) => assert.strictEqual(a, b);

teste('dados válidos não geram erros', () => eq(Object.keys(A.validar(valido(), [])).length, 0));
teste('nome com menos de 3 caracteres (após trim) é recusado', () => eq(typeof A.validar({ ...valido(), nome: ' ab ' }, []).nome, 'string'));
teste('e-mail inválido é recusado', () => eq(typeof A.validar({ ...valido(), email: 'sem-arroba' }, []).email, 'string'));
teste('e-mail duplicado é recusado ignorando maiúsculas e espaços', () => {
  const lista = [valido()];
  eq(typeof A.validar({ ...valido(), email: '  TESTE1@Exemplo.com ' }, lista).email, 'string');
});
teste('curso fora da lista é recusado', () => eq(typeof A.validar({ ...valido(), curso: 'Invalido' }, []).curso, 'string'));
teste('período fora de 1 a 10 é recusado', () => {
  eq(typeof A.validar({ ...valido(), periodo: '11' }, []).periodo, 'string');
  eq(typeof A.validar({ ...valido(), periodo: '' }, []).periodo, 'string');
});
teste('experiência fora das opções é recusada', () => eq(typeof A.validar({ ...valido(), experiencia: 'guru' }, []).experiencia, 'string'));
teste('sem consentimento LGPD é recusado', () => eq(typeof A.validar({ ...valido(), lgpd: false }, []).lgpd, 'string'));

teste('escaparCsv não altera texto simples', () => eq(A.escaparCsv('Ana'), 'Ana'));
teste('escaparCsv envolve em aspas campo com ponto e vírgula e dobra aspas', () => eq(A.escaparCsv('a;"b"'), '"a;""b"""'));
teste('escaparCsv envolve em aspas campo com quebra de linha', () => eq(A.escaparCsv('a\nb'), '"a\nb"'));
teste('escaparCsv neutraliza início de fórmula', () => {
  for (const c of ['=', '+', '-', '@']) eq(A.escaparCsv(`${c}1`), `'${c}1`);
});

teste('gerarCsv começa com BOM, usa ; e \\r\\n', () => {
  const csv = A.gerarCsv([valido()]);
  eq(csv.charAt(0), '﻿');
  const linhas = csv.slice(1).split('\r\n');
  eq(linhas[0], 'Nome;E-mail;Curso;Período;Experiência com IA;Inscrito em');
  eq(linhas[1].startsWith('Aluno Teste;teste1@exemplo.com;Direito;3º;Básica;'), true);
});
teste('gerarCsv com lista vazia gera só o cabeçalho', () => eq(A.gerarCsv([]).slice(1).split('\r\n').length, 1));

const lista3 = [{ ...valido(), curso: 'Direito' }, { ...valido(), email: 'b@exemplo.com', curso: 'Design' }, { ...valido(), email: 'c@exemplo.com', curso: 'Direito' }];
teste('filtrarPorCurso com curso vazio devolve todos', () => eq(A.filtrarPorCurso(lista3, '').length, 3));
teste('filtrarPorCurso devolve só o curso escolhido', () => {
  const r = A.filtrarPorCurso(lista3, 'Direito');
  eq(r.length, 2);
  eq(r.every((i) => i.curso === 'Direito'), true);
});
teste('filtrarPorCurso sem correspondência devolve lista vazia', () => eq(A.filtrarPorCurso(lista3, 'Medicina').length, 0));

teste('removerInscrito tira só o e-mail indicado, ignorando maiúsculas', () => {
  const r = A.removerInscrito(lista3, ' B@Exemplo.com ');
  eq(r.length, 2);
  eq(r.some((i) => i.email === 'b@exemplo.com'), false);
});
teste('removerInscrito com e-mail inexistente mantém a lista', () => eq(A.removerInscrito(lista3, 'x@exemplo.com').length, 3));
teste('removerInscrito não altera a lista original', () => { A.removerInscrito(lista3, 'b@exemplo.com'); eq(lista3.length, 3); });
teste('e-mail removido pode ser inscrito de novo', () => {
  const sem = A.removerInscrito([valido()], 'teste1@exemplo.com');
  eq(Object.keys(A.validar(valido(), sem)).length, 0);
});

// Médio 1: chaves do protótipo não são níveis de experiência válidos.
teste('experiência com nome de propriedade do protótipo é recusada', () => {
  for (const x of ['constructor', 'toString', '__proto__', 'hasOwnProperty']) {
    eq(typeof A.validar({ ...valido(), experiencia: x }, []).experiencia, 'string');
  }
});

// Médio 2: dados do localStorage são entrada não confiável.
teste('escaparCsv neutraliza fórmula precedida de tab ou CR', () => {
  eq(A.escaparCsv('\t=1+1'), "'\t=1+1");
  eq(A.escaparCsv('\r=1+1').startsWith(`"'`), true);
});
teste('sanitizarLista com valor que não é lista devolve lista vazia', () => {
  for (const x of [null, undefined, {}, 'texto', 5]) eq(A.sanitizarLista(x).length, 0);
});
teste('sanitizarLista descarta null, primitivos e objetos inválidos', () => {
  const lista = [null, 7, 'x', [], { nome: 'a' }, { ...valido(), experiencia: 'toString' }, valido()];
  eq(A.sanitizarLista(lista).length, 1);
});
teste('sanitizarLista exige nome e e-mail como texto', () => {
  eq(A.sanitizarLista([{ ...valido(), nome: { toString: () => 'Fulano' } }]).length, 0);
  eq(A.sanitizarLista([{ ...valido(), email: ['a@b.co'] }]).length, 0);
});
teste('sanitizarLista descarta e-mail repetido e mantém o primeiro', () => {
  const r = A.sanitizarLista([valido(), { ...valido(), nome: 'Outro Nome', email: 'TESTE1@exemplo.com' }]);
  eq(r.length, 1);
  eq(r[0].nome, 'Aluno Teste');
});
teste('sanitizarLista aplica trim em nome e e-mail', () => {
  const r = A.sanitizarLista([{ ...valido(), nome: '\t=cmd|x ', email: ' teste1@exemplo.com ' }]);
  eq(r[0].nome, '=cmd|x');
  eq(r[0].email, 'teste1@exemplo.com');
});
teste('sanitizarLista troca data inválida por texto vazio', () => {
  eq(A.sanitizarLista([{ ...valido(), inscritoEm: 'lixo' }])[0].inscritoEm, '');
  eq(A.sanitizarLista([{ ...valido(), inscritoEm: '2026-10-01T12:00:00.000Z' }])[0].inscritoEm, '2026-10-01T12:00:00.000Z');
});
teste('sanitizarLista e validar recusam experiência em formato de lista', () => {
  eq(A.sanitizarLista([{ ...valido(), experiencia: ['basica'] }]).length, 0);
  eq(typeof A.validar({ ...valido(), experiencia: ['basica'] }, []).experiencia, 'string');
});
teste('gerarCsv de lista sanitizada com entradas corrompidas não lança erro', () => {
  A.gerarCsv(A.sanitizarLista([null, { nome: 1 }, valido()]));
});

const falhas = resultados.filter(([ok]) => !ok);
resultados.forEach(([ok, msg]) => console.log(`${ok ? 'PASSOU' : 'FALHOU'}  ${msg}`));
console.log(`\n${resultados.length - falhas.length}/${resultados.length} passaram`);
if (typeof document !== 'undefined') {
  document.body.innerHTML = '';
  const pre = document.createElement('pre');
  pre.textContent = resultados.map(([ok, m]) => `${ok ? '✔' : '✘'} ${m}`).join('\n') + `\n\n${resultados.length - falhas.length}/${resultados.length} passaram`;
  document.body.appendChild(pre);
}
if (falhas.length && typeof process !== 'undefined') process.exit(1);
