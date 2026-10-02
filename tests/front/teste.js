// Testes das funções puras de publico/app.js. Dados fictícios apenas.
// Node: `node tests/front/teste.js`  |  Navegador: abrir tests/front/teste.html
const assert = typeof require !== 'undefined' ? require('assert') : { strictEqual: (a, b) => { if (a !== b) throw new Error(`esperado ${JSON.stringify(b)}, veio ${JSON.stringify(a)}`); } };
const A = typeof module !== 'undefined' ? require('../../publico/app.js') : App;

const valido = () => ({ nome: 'Aluno Teste', email: 'teste1@exemplo.com', curso: 'Direito', periodo: '3', experiencia: 'basica', lgpd: true });
const resultados = [];
function teste(nome, fn) {
  try { fn(); resultados.push([true, nome]); } catch (e) { resultados.push([false, `${nome}: ${e.message}`]); }
}
const eq = (a, b) => assert.strictEqual(a, b);
const temErro = (d, campo) => eq(typeof A.validar(d)[campo], 'string');

teste('dados válidos não geram erros', () => eq(Object.keys(A.validar(valido())).length, 0));
teste('nome curto (após trim) é recusado', () => temErro({ ...valido(), nome: ' ab ' }, 'nome'));
teste('nome com mais de 100 caracteres é recusado', () => temErro({ ...valido(), nome: 'x'.repeat(101) }, 'nome'));
teste('e-mail inválido é recusado', () => temErro({ ...valido(), email: 'sem-arroba' }, 'email'));
teste('e-mail com mais de 254 caracteres é recusado', () => temErro({ ...valido(), email: 'a@' + 'b'.repeat(250) + '.co' }, 'email'));
teste('curso fora da lista é recusado', () => temErro({ ...valido(), curso: 'Invalido' }, 'curso'));
teste('período fora de 1 a 10 é recusado', () => {
  temErro({ ...valido(), periodo: '11' }, 'periodo');
  temErro({ ...valido(), periodo: '' }, 'periodo');
});
teste('experiência fora das opções é recusada', () => temErro({ ...valido(), experiencia: 'guru' }, 'experiencia'));
teste('experiência com nome de propriedade do protótipo é recusada', () => {
  for (const x of ['constructor', 'toString', '__proto__', 'hasOwnProperty']) temErro({ ...valido(), experiencia: x }, 'experiencia');
});
teste('experiência em formato de lista é recusada', () => temErro({ ...valido(), experiencia: ['basica'] }, 'experiencia'));
teste('sem consentimento LGPD é recusado', () => temErro({ ...valido(), lgpd: false }, 'lgpd'));

teste('traduzirErros troca consentimento por lgpd', () => {
  const r = A.traduzirErros({ consentimento: 'a', nome: 'b' });
  eq(r.campos.lgpd, 'a');
  eq(r.campos.nome, 'b');
  eq(r.geral, '');
});
teste('traduzirErros separa o erro geral', () => eq(A.traduzirErros({ _geral: 'x' }).geral, 'x'));
teste('traduzirErros com campo desconhecido vira mensagem geral', () => {
  const r = A.traduzirErros({ admin: 'x' });
  eq(Object.keys(r.campos).length, 0);
  eq(typeof r.geral, 'string');
  eq(r.geral.length > 0, true);
});
teste('traduzirErros sem objeto devolve mensagem geral', () => eq(A.traduzirErros(undefined).geral.length > 0, true));

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
