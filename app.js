const CHAVE = 'inscritos-minicurso';
const CURSOS = ['Administração', 'Ciência da Computação', 'Direito', 'Engenharia', 'Medicina', 'Psicologia', 'Design', 'Comunicação', 'Outro'];
const PERIODOS = Array.from({ length: 10 }, (_, i) => String(i + 1));
const EXPERIENCIAS = { nenhuma: 'Nenhuma', basica: 'Básica', avancada: 'Avançada' };
const CAMPOS = ['nome', 'email', 'curso', 'periodo', 'experiencia', 'lgpd'];

const normalizarEmail = (e) => String(e).trim().toLowerCase();

// Retorna { campo: mensagem } só para os campos inválidos.
function validar(d, inscritos) {
  const erros = {};
  if (String(d.nome || '').trim().length < 3) erros.nome = 'Informe seu nome completo (mínimo 3 caracteres).';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(d.email || '').trim())) erros.email = 'Informe um e-mail válido, como nome@exemplo.com.';
  else if (inscritos.some((i) => normalizarEmail(i.email) === normalizarEmail(d.email))) erros.email = 'Este e-mail já está inscrito.';
  if (!CURSOS.includes(d.curso)) erros.curso = 'Selecione seu curso.';
  if (!PERIODOS.includes(String(d.periodo))) erros.periodo = 'Selecione seu período (1º a 10º).';
  if (typeof d.experiencia !== 'string' || !Object.hasOwn(EXPERIENCIAS, d.experiencia)) erros.experiencia = 'Escolha seu nível de experiência com IA.';
  if (d.lgpd !== true) erros.lgpd = 'É necessário consentir com o uso dos dados para se inscrever.';
  return erros;
}

function escaparCsv(valor) {
  let s = String(valor);
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`; // evita injeção de fórmula no Excel
  return /[;"\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function gerarCsv(inscritos) {
  const linhas = [['Nome', 'E-mail', 'Curso', 'Período', 'Experiência com IA', 'Inscrito em']];
  for (const i of inscritos) {
    linhas.push([i.nome, i.email, i.curso, `${i.periodo}º`, EXPERIENCIAS[i.experiencia],
      i.inscritoEm ? new Date(i.inscritoEm).toLocaleString('pt-BR') : '']);
  }
  return '﻿' + linhas.map((l) => l.map(escaparCsv).join(';')).join('\r\n');
}

const filtrarPorCurso = (inscritos, curso) => (curso ? inscritos.filter((i) => i.curso === curso) : inscritos);

const removerInscrito = (inscritos, email) => inscritos.filter((i) => normalizarEmail(i.email) !== normalizarEmail(email));

// O localStorage é entrada não confiável: só passa o que o formulário aceitaria.
function sanitizarLista(lista) {
  if (!Array.isArray(lista)) return [];
  const aceitos = [];
  for (const r of lista) {
    if (!r || typeof r !== 'object' || ![r.nome, r.email, r.curso, r.experiencia].every((v) => typeof v === 'string')) continue;
    const reg = { nome: r.nome.trim(), email: r.email.trim(), curso: r.curso, periodo: String(r.periodo), experiencia: r.experiencia,
      inscritoEm: typeof r.inscritoEm === 'string' && !isNaN(Date.parse(r.inscritoEm)) ? r.inscritoEm : '' };
    // lgpd: true porque o consentimento já foi exigido quando o registro foi criado
    if (Object.keys(validar({ ...reg, lgpd: true }, aceitos)).length === 0) aceitos.push(reg);
  }
  return aceitos;
}

const App = { validar, escaparCsv, gerarCsv, filtrarPorCurso, removerInscrito, sanitizarLista };
if (typeof module !== 'undefined') module.exports = App;

if (typeof document !== 'undefined' && document.getElementById('form')) {
  const $ = (id) => document.getElementById(id);
  const form = $('form');
  let inscritos = [];

  function aviso(texto) { $('aviso').textContent = texto; $('aviso').hidden = !texto; }

  function carregar() {
    try {
      const bruto = JSON.parse(localStorage.getItem(CHAVE) || '[]');
      if (!Array.isArray(bruto)) throw new Error('formato inválido');
      const lista = sanitizarLista(bruto);
      if (lista.length < bruto.length) aviso('Alguns registros salvos eram inválidos e foram ignorados.');
      return lista;
    } catch (e) {
      aviso('Não foi possível ler os dados salvos neste navegador. A lista começou vazia.');
      return [];
    }
  }

  function salvar() {
    try { localStorage.setItem(CHAVE, JSON.stringify(inscritos)); } catch (e) {
      aviso('Não foi possível salvar neste navegador. As inscrições se perdem ao fechar a página.');
    }
  }

  function renderizar() {
    const curso = $('filtro-curso').value;
    const visiveis = filtrarPorCurso(inscritos, curso);
    $('total').textContent = curso
      ? `Mostrando ${visiveis.length} de ${inscritos.length} inscritos (${curso})`
      : `Total: ${inscritos.length} ${inscritos.length === 1 ? 'inscrito' : 'inscritos'}`;
    $('exportar').disabled = inscritos.length === 0;
    $('filtro-curso').disabled = inscritos.length === 0;
    $('vazio').textContent = inscritos.length ? 'Nenhum inscrito neste curso.' : 'Nenhuma inscrição ainda.';
    $('vazio').hidden = visiveis.length > 0;
    $('tabela').hidden = visiveis.length === 0;
    const corpo = $('corpo');
    corpo.replaceChildren();
    for (const i of visiveis) {
      const tr = document.createElement('tr');
      const celulas = [['Nome', i.nome], ['E-mail', i.email], ['Curso', i.curso], ['Período', `${i.periodo}º`], ['Experiência com IA', EXPERIENCIAS[i.experiencia]]];
      for (const [rotulo, valor] of celulas) {
        const td = document.createElement('td');
        td.dataset.rotulo = rotulo;
        td.textContent = valor;
        tr.appendChild(td);
      }
      const acao = document.createElement('td');
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'botao remover';
      btn.textContent = 'Remover';
      btn.dataset.email = i.email;
      btn.setAttribute('aria-label', `Remover inscrição de ${i.nome}`);
      acao.appendChild(btn);
      tr.appendChild(acao);
      corpo.appendChild(tr);
    }
  }

  function lerDados() {
    const f = new FormData(form);
    return { nome: f.get('nome') || '', email: f.get('email') || '', curso: f.get('curso') || '',
      periodo: f.get('periodo') || '', experiencia: f.get('experiencia') || '', lgpd: f.get('lgpd') === 'on' };
  }

  // Elemento que recebe aria-invalid e o link do resumo de erros.
  const alvo = (campo) => (campo === 'experiencia' ? $('grupo-experiencia') : $(campo));
  const alvoFoco = (campo) => (campo === 'experiencia' ? $('exp-nenhuma') : $(campo));

  function mostrarErro(campo, msg) {
    $(`erro-${campo}`).textContent = msg || '';
    if (msg) alvo(campo).setAttribute('aria-invalid', 'true'); else alvo(campo).removeAttribute('aria-invalid');
  }

  function limparErros() { CAMPOS.forEach((c) => mostrarErro(c, '')); $('resumo').hidden = true; }

  function mostrarResumo(erros) {
    const lista = $('resumo-lista');
    lista.replaceChildren();
    for (const [campo, msg] of Object.entries(erros)) {
      const a = document.createElement('a');
      a.href = `#${alvoFoco(campo).id}`;
      a.textContent = msg;
      const li = document.createElement('li');
      li.appendChild(a);
      lista.appendChild(li);
    }
    $('resumo').hidden = false;
    $('resumo').focus();
  }

  // Valida um campo só (blur/input), sem tocar nos outros.
  function validarCampo(campo) {
    mostrarErro(campo, validar(lerDados(), inscritos)[campo]);
  }

  CURSOS.forEach((c) => $('curso').add(new Option(c, c)));
  PERIODOS.forEach((p) => $('periodo').add(new Option(`${p}º`, p)));
  CURSOS.forEach((c) => $('filtro-curso').add(new Option(c, c)));
  $('filtro-curso').addEventListener('change', renderizar);

  $('corpo').addEventListener('click', (e) => {
    const btn = e.target.closest('.remover');
    if (!btn) return;
    const inscrito = inscritos.find((i) => i.email === btn.dataset.email);
    if (!inscrito || !confirm(`Remover a inscrição de ${inscrito.nome}? Esta ação não pode ser desfeita.`)) return;
    inscritos = removerInscrito(inscritos, inscrito.email);
    salvar();
    renderizar();
    $('total').focus(); // o botão clicado sumiu: leva o foco para o total
  });

  form.addEventListener('focusout', (e) => {
    const campo = e.target.name;
    if (!CAMPOS.includes(campo)) return;
    // Campo vazio só acusa erro no envio (ou se já estava inválido); rádio e checkbox idem.
    const preenchido = ['nome', 'email', 'curso', 'periodo'].includes(campo) && e.target.value !== '';
    if (preenchido || alvo(campo).getAttribute('aria-invalid')) validarCampo(campo);
  });
  form.addEventListener('input', (e) => {
    const campo = e.target.name;
    if (CAMPOS.includes(campo) && alvo(campo).getAttribute('aria-invalid')) validarCampo(campo);
  });

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    $('sucesso').hidden = true;
    const dados = lerDados();
    const erros = validar(dados, inscritos);
    limparErros();
    if (Object.keys(erros).length) {
      for (const [campo, msg] of Object.entries(erros)) mostrarErro(campo, msg);
      mostrarResumo(erros);
      return;
    }
    inscritos.push({ nome: dados.nome.trim(), email: dados.email.trim(), curso: dados.curso, periodo: dados.periodo,
      experiencia: dados.experiencia, inscritoEm: new Date().toISOString() });
    salvar();
    renderizar();
    form.reset();
    $('sucesso').textContent = `Inscrição de ${dados.nome.trim()} confirmada!`;
    $('sucesso').hidden = false;
  });

  $('exportar').addEventListener('click', () => {
    const url = URL.createObjectURL(new Blob([gerarCsv(inscritos)], { type: 'text/csv;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'inscritos-minicurso.csv';
    a.click();
    URL.revokeObjectURL(url);
  });

  inscritos = carregar();
  renderizar();
}
