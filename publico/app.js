const CURSOS = ['Administração', 'Ciência da Computação', 'Direito', 'Engenharia', 'Medicina', 'Psicologia', 'Design', 'Comunicação', 'Outro'];
const PERIODOS = Array.from({ length: 10 }, (_, i) => String(i + 1));
const EXPERIENCIAS = { nenhuma: 'Nenhuma', basica: 'Básica', avancada: 'Avançada' };
const CAMPOS = ['nome', 'email', 'curso', 'periodo', 'experiencia', 'lgpd'];

// Validação só para feedback rápido. O servidor valida de novo e é quem decide.
function validar(d) {
  const erros = {};
  const nome = String(d.nome || '').trim();
  const email = String(d.email || '').trim();
  if (nome.length < 3 || nome.length > 100) erros.nome = 'Informe seu nome completo (3 a 100 caracteres).';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254) erros.email = 'Informe um e-mail válido, como nome@exemplo.com.';
  if (!CURSOS.includes(d.curso)) erros.curso = 'Selecione seu curso.';
  if (!PERIODOS.includes(String(d.periodo))) erros.periodo = 'Selecione seu período (1º a 10º).';
  if (typeof d.experiencia !== 'string' || !Object.hasOwn(EXPERIENCIAS, d.experiencia)) erros.experiencia = 'Escolha seu nível de experiência com IA.';
  if (d.lgpd !== true) erros.lgpd = 'É necessário consentir com o uso dos dados para se inscrever.';
  return erros;
}

// Converte { campo: mensagem } do servidor para os nomes dos campos desta página.
function traduzirErros(erros) {
  const campos = {};
  let geral = '';
  if (erros && typeof erros === 'object') {
    for (const [campo, msg] of Object.entries(erros)) {
      const nome = campo === 'consentimento' ? 'lgpd' : campo;
      if (CAMPOS.includes(nome)) campos[nome] = String(msg);
      else if (campo === '_geral') geral = String(msg);
    }
  }
  if (!Object.keys(campos).length && !geral) geral = 'Não foi possível validar os dados. Revise o formulário.';
  return { campos, geral };
}

const App = { validar, traduzirErros };
if (typeof module !== 'undefined') module.exports = App;

if (typeof document !== 'undefined' && document.getElementById('form')) {
  const $ = (id) => document.getElementById(id);
  const form = $('form');

  function avisar(texto) { $('aviso').textContent = texto; $('aviso').hidden = !texto; }

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

  function limparErros() { CAMPOS.forEach((c) => mostrarErro(c, '')); $('resumo').hidden = true; avisar(''); }

  function mostrarErros(erros) {
    const lista = $('resumo-lista');
    lista.replaceChildren();
    for (const [campo, msg] of Object.entries(erros)) {
      mostrarErro(campo, msg);
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
  function validarCampo(campo) { mostrarErro(campo, validar(lerDados())[campo]); }

  CURSOS.forEach((c) => $('curso').add(new Option(c, c)));
  PERIODOS.forEach((p) => $('periodo').add(new Option(`${p}º`, p)));

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

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    $('sucesso').hidden = true;
    const dados = lerDados();
    const erros = validar(dados);
    limparErros();
    if (Object.keys(erros).length) { mostrarErros(erros); return; }

    const botao = form.querySelector('button[type="submit"]');
    botao.disabled = true;
    try {
      const r = await fetch('/api/inscricoes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nome: dados.nome.trim(), email: dados.email.trim(), curso: dados.curso,
          periodo: Number(dados.periodo), experiencia: dados.experiencia, consentimento: true }),
      });
      if (r.status === 201) {
        form.reset();
        $('sucesso').textContent = (await r.json()).mensagem;
        $('sucesso').hidden = false;
      } else if (r.status === 422) {
        const { campos, geral } = traduzirErros((await r.json()).erros);
        if (Object.keys(campos).length) mostrarErros(campos);
        if (geral) avisar(geral);
      } else if (r.status === 429) {
        avisar('Muitas tentativas. Aguarde um instante e tente de novo.');
      } else {
        avisar('Não foi possível enviar sua inscrição. Tente novamente mais tarde.');
      }
    } catch (err) {
      avisar('Sem conexão com o servidor. Verifique a internet e tente novamente.');
    } finally {
      botao.disabled = false;
    }
  });
}
