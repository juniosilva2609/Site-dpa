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
})();
