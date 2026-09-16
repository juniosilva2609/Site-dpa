"""Gera o PDF de extrato do Sicoob no mesmo layout do internet banking
(modelo enviado pelo usuário: "Extrato de Conta Corrente" impresso do
SISBR/Internet Banking).

A API do Sicoob não exporta PDF nativo — este módulo monta um HTML
equivalente ao modelo do banco e usa o Chromium (via Playwright) para
"imprimir" em PDF, igual ao que o próprio internet banking faz no
navegador.

Importante: só usamos aqui campos que a API realmente devolve
(saldoAtual, saldoAnterior, saldoLimite, saldoBloqueado,
saldoBloqueioJudicial, transacoes). Seções do modelo original que dependem
de dados que essa API não fornece (juros/tarifas provisionados, encargos a
vencer, condições do cheque especial) aparecem como "não disponível via
API" — nunca preenchidas com valor inventado.
"""

from datetime import date, datetime

CHROMIUM_PATH = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def _fmt_moeda(valor, sinal_credito_debito: bool = True) -> str:
    v = float(valor)
    texto = f"{abs(v):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if not sinal_credito_debito:
        return f"R$ {texto}"
    sufixo = "D" if v < 0 else "C"
    return f"R$ {texto}{sufixo}"


def _agrupar_por_dia(transacoes: list[dict]) -> list[tuple[str, list[dict]]]:
    grupos: dict[str, list[dict]] = {}
    for t in transacoes:
        dia = t["data"][:10]
        grupos.setdefault(dia, []).append(t)
    dias_desc = sorted(grupos.keys(), reverse=True)
    return [(dia, sorted(grupos[dia], key=lambda t: t["data"], reverse=True)) for dia in dias_desc]


def _saldos_por_dia(transacoes: list[dict], saldo_anterior: float) -> dict[str, float]:
    """Saldo acumulado ao final de cada dia, andando em ordem cronológica
    a partir do saldo anterior ao período (mesmo valor que a API devolve
    em `saldoAnterior`)."""
    ordenadas = sorted(transacoes, key=lambda t: t["data"])
    saldo = saldo_anterior
    saldo_final_do_dia: dict[str, float] = {}
    for t in ordenadas:
        dia = t["data"][:10]
        delta = float(t["valor"]) if t.get("tipo") == "CREDITO" else -float(t["valor"])
        saldo += delta
        saldo_final_do_dia[dia] = saldo
    return saldo_final_do_dia


def _linha_transacao(t: dict) -> str:
    hora = datetime.fromisoformat(t["data"]).strftime("%d/%m")
    doc = t.get("numeroDocumento") or ""
    hist = t.get("descricao", "")
    complemento = t.get("descInfComplementar", "")
    valor = float(t["valor"])
    valor_fmt = _fmt_moeda(-valor if t.get("tipo") == "DEBITO" else valor)
    cor = "#c0392b" if t.get("tipo") == "DEBITO" else "#1e7a4f"
    return f"""
    <tr>
      <td class="col-data">{hora}</td>
      <td class="col-doc">{doc}</td>
      <td class="col-hist">{hist}<br><span class="complemento">{complemento}</span></td>
      <td class="col-valor" style="color:{cor}">{valor_fmt}</td>
    </tr>"""


def _linha_saldo_dia(dia_iso: str, saldo: float) -> str:
    dia_fmt = datetime.fromisoformat(dia_iso).strftime("%d/%m")
    cor = "#c0392b" if saldo < 0 else "#1e7a4f"
    return f"""
    <tr class="linha-saldo">
      <td class="col-data">{dia_fmt}</td>
      <td class="col-doc"></td>
      <td class="col-hist">SALDO DO DIA</td>
      <td class="col-valor" style="color:{cor}">{_fmt_moeda(saldo)}</td>
    </tr>"""


def gerar_pdf(
    dados: dict,
    conta: str,
    cooperativa: str,
    cooperativa_nome: str,
    razao_social: str,
    inicio: date,
    fim: date,
) -> bytes:
    transacoes = dados.get("transacoes", [])
    saldo_anterior = float(dados.get("saldoAnterior", 0))
    saldo_atual = float(dados.get("saldoAtual", 0))
    saldo_limite = float(dados.get("saldoLimite", 0))
    saldo_bloqueado = float(dados.get("saldoBloqueado", 0))
    saldo_bloqueio_judicial = float(dados.get("saldoBloqueioJudicial", 0))
    saldo_disponivel = saldo_atual + saldo_limite - saldo_bloqueado

    dias = _agrupar_por_dia(transacoes)
    saldos_dia = _saldos_por_dia(transacoes, saldo_anterior)

    linhas_html = []
    for dia_iso, txs in dias:
        for t in txs:
            linhas_html.append(_linha_transacao(t))
        linhas_html.append(_linha_saldo_dia(dia_iso, saldos_dia[dia_iso]))
    linhas_html.append(f"""
    <tr class="linha-saldo">
      <td class="col-data">{inicio.strftime('%d/%m')}</td>
      <td class="col-doc"></td>
      <td class="col-hist">SALDO ANTERIOR</td>
      <td class="col-valor" style="color:{'#c0392b' if saldo_anterior < 0 else '#1e7a4f'}">{_fmt_moeda(saldo_anterior)}</td>
    </tr>""")

    agora = datetime.now().strftime("%d/%m/%Y - %H:%M:%S")

    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
    body {{ font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #222; margin: 24px; }}
    .cabecalho {{ display:flex; align-items:center; gap:10px; border-bottom: 2px solid #00995d; padding-bottom: 8px; }}
    .cabecalho .logo {{ color:#00995d; font-weight:bold; font-size:20px; }}
    .cabecalho .titulos {{ font-size:11px; font-weight:bold; line-height:1.3; }}
    .titulo-extrato {{ display:flex; justify-content:space-between; align-items:center; margin-top:14px; font-weight:bold; font-size:14px; }}
    .info {{ margin-top:10px; display:grid; grid-template-columns:100px 1fr; row-gap:2px; }}
    .info b {{ font-weight:bold; }}
    h2.secao {{ font-size:12px; margin:18px 0 6px; border-bottom:1px solid #ccc; padding-bottom:4px; }}
    table {{ width:100%; border-collapse:collapse; }}
    th {{ text-align:left; border-bottom:1px solid #999; padding:4px 6px; font-size:11px; }}
    th.col-valor, td.col-valor {{ text-align:right; }}
    td {{ padding:4px 6px; vertical-align:top; font-size:11px; }}
    .complemento {{ color:#666; font-size:10px; }}
    tr.linha-saldo td {{ font-weight:bold; background:#f2f6f4; border-top:1px solid #ddd; border-bottom:1px solid #ddd; }}
    .resumo-tabela {{ width:100%; border-collapse:collapse; margin-top:4px; }}
    .resumo-tabela td {{ padding:3px 0; font-size:11px; }}
    .resumo-tabela td.valor {{ text-align:right; }}
    .resumo-tabela tr.destaque td {{ font-weight:bold; }}
    .rodape {{ margin-top: 24px; font-size:10px; color:#666; }}
    .nota {{ font-size:9px; color:#999; font-style:italic; }}
    </style></head><body>

    <div class="cabecalho">
      <div class="logo">&#10003; SICOOB</div>
      <div class="titulos">SISTEMA DE COOPERATIVAS DE CRÉDITO DO BRASIL<br>PLATAFORMA DE SERVIÇOS FINANCEIROS DO SICOOB - SISBR</div>
    </div>

    <div class="titulo-extrato">
      <span>&#128203; EXTRATO DE CONTA CORRENTE</span>
      <span>{agora}</span>
    </div>

    <div class="info">
      <b>Cooperativa:</b><span>{cooperativa} / {cooperativa_nome}</span>
      <b>Conta:</b><span>{conta} / {razao_social}</span>
      <b>Periodo:</b><span>{inicio.strftime('%d/%m/%Y')} - {fim.strftime('%d/%m/%Y')}</span>
    </div>

    <h2 class="secao">&#128197; HISTÓRICO DE MOVIMENTAÇÃO</h2>
    <table>
      <thead><tr><th class="col-data">Data</th><th class="col-doc">Documento</th><th class="col-hist">Histórico</th><th class="col-valor">Valor</th></tr></thead>
      <tbody>{"".join(linhas_html)}</tbody>
    </table>

    <h2 class="secao">&#128197; RESUMO</h2>
    <table class="resumo-tabela">
      <tr><td>Saldo em conta:</td><td class="valor">{_fmt_moeda(saldo_atual)}</td></tr>
      <tr><td>Cheque especial contratado:</td><td class="valor">{_fmt_moeda(saldo_limite, False)}</td></tr>
      <tr><td>Juros vencidos provisionados:</td><td class="valor">não disponível via API</td></tr>
      <tr><td>Tarifas vencidas provisionadas:</td><td class="valor">não disponível via API</td></tr>
      <tr class="destaque"><td>Saldo disponível:</td><td class="valor">{_fmt_moeda(saldo_disponivel)}</td></tr>
      <tr><td>Saldo bloqueado (cheques):</td><td class="valor">{_fmt_moeda(saldo_bloqueado, False)}</td></tr>
      <tr><td>Saldo bloqueado (judicial):</td><td class="valor">{_fmt_moeda(saldo_bloqueio_judicial, False)}</td></tr>
    </table>

    <h2 class="secao">OUTRAS INFORMAÇÕES</h2>
    <p class="nota">Condições de cheque especial (vencimento, taxa, CET) e encargos a vencer não são
    fornecidos por este endpoint da API do Sicoob — não exibidos para não apresentar valor não confirmado.</p>

    <h2 class="secao">&#8505; INFORMAÇÕES</h2>
    <p>SAC: 0800 724 4420 / OUVIDORIA SICOOB: 08007250996</p>

    <div class="rodape">Gerado automaticamente a partir da API oficial do Sicoob — DPA / Fechamento Bancário</div>
    </body></html>"""

    import os as _os

    from playwright.sync_api import sync_playwright

    # CHROMIUM_PATH aponta para o Chromium pré-instalado neste ambiente
    # Claude Code. Fora dele, roda com o Chromium padrão do Playwright
    # (é preciso ter rodado `playwright install chromium` antes).
    executable_path = CHROMIUM_PATH if _os.path.exists(CHROMIUM_PATH) else None

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable_path)
        page = browser.new_page()
        page.set_content(html)
        pdf_bytes = page.pdf(format="A4", margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"})
        browser.close()
    return pdf_bytes
