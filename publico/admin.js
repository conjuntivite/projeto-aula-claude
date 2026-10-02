// A CSP bloqueia onclick inline, então a confirmação é feita aqui.
document.addEventListener('submit', (e) => {
  const msg = e.target.dataset.confirmar;
  if (msg && !confirm(msg)) e.preventDefault();
});
