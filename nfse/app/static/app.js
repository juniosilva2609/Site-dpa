// Contador de caracteres da descrição e confirmações de ações perigosas (sem JS inline por causa da CSP).
(function () {
  var LIMITE = 1297;
  document.querySelectorAll('textarea[data-contador]').forEach(function (ta) {
    var alvo = document.getElementById(ta.dataset.contador);
    function atualizar() {
      var n = ta.value.split(/\s+/).filter(Boolean).join(' ').length;
      alvo.textContent = n + ' / ' + LIMITE;
      alvo.style.color = n > LIMITE ? '#b00020' : '';
      alvo.style.fontWeight = n > LIMITE ? '700' : '';
    }
    ta.addEventListener('input', atualizar);
    atualizar();
  });
  document.querySelectorAll('form[data-confirmar]').forEach(function (f) {
    f.addEventListener('submit', function (e) { if (!window.confirm(f.dataset.confirmar)) e.preventDefault(); });
  });
  document.querySelectorAll('button[disabled]').forEach(function (b) { b.title = 'Corrija os itens em vermelho acima'; });
  // dica (tooltip) dos gráficos: segue o mouse; também abre ao focar com teclado/toque
  var dica = document.getElementById('dica');
  if (dica) {
    document.addEventListener('mouseover', function (e) {
      var alvo = e.target.closest ? e.target.closest('[data-tip]') : null;
      if (!alvo) { dica.hidden = true; return; }
      dica.textContent = alvo.getAttribute('data-tip'); dica.hidden = false;
    });
    document.addEventListener('mousemove', function (e) {
      if (dica.hidden) return;
      dica.style.left = Math.min(e.clientX + 14, window.innerWidth - dica.offsetWidth - 8) + 'px';
      dica.style.top = (e.clientY + 16) + 'px';
    });
    document.addEventListener('click', function (e) {
      var alvo = e.target.closest ? e.target.closest('[data-tip]') : null;   // toque no celular
      if (alvo) { dica.textContent = alvo.getAttribute('data-tip'); dica.hidden = false; dica.style.left = '12px'; dica.style.top = (e.clientY + 16) + 'px'; }
    });
  }
  document.querySelectorAll('[data-imprimir]').forEach(function (b) { b.addEventListener('click', function () { window.print(); }); });
})();
