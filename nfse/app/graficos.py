# -*- coding: utf-8 -*-
"""Gráficos em SVG puro, gerados no servidor (sem bibliotecas nem CDN: a CSP do sistema só permite recursos próprios).

Segue as regras de visualização: marcas finas; coluna <= 24 px com topo arredondado e base reta; grade e eixos
discretos; no máximo 6 cores categóricas (o resto vira "Outros"); texto nunca usa a cor da série (a cor fica numa
marca ao lado: bolinha da legenda); sempre há legenda/tabela com os valores. As cores vêm de variáveis CSS
(`--s1`..`--s6`, claro/escuro) definidas em style.css."""

import math
from html import escape

from . import util


def _fmt_tip(rotulo: str, valor: str, extra: str = "") -> str:
    return escape(f"{rotulo}: {valor}" + (f" ({extra})" if extra else ""), quote=True)


def _bonito(maximo: float, ticks: int = 4) -> tuple[float, float]:
    """(teto, passo) 'redondos' (1-2-5) para o eixo y."""
    if maximo <= 0:
        return 1.0, 0.25
    bruto = maximo / ticks
    pot = 10 ** math.floor(math.log10(bruto))
    for mult in (1, 2, 2.5, 5, 10):
        passo = mult * pot
        if passo * ticks >= maximo:
            return passo * ticks, passo
    return maximo, bruto


def _topo_arredondado(x, y, w, h, r=4) -> str:
    r = min(r, w / 2, h)
    return (f"M{x:.1f},{y + h:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} H{x + w - r:.1f} "
            f"Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{y + h:.1f} Z")


def colunas(dados: list[dict], rotulo_eixo: str = "Faturamento por mês") -> str:
    """dados: [{mes: 'AAAA-MM', valor: centavos, qtd}]. Uma série só -> uma cor, sem legenda (o título diz o que é)."""
    if not dados:
        return '<p class="suave">Sem dados no período.</p>'
    W, H, ml, mr, mt, mb = 720, 290, 54, 12, 30, 34
    pw, ph = W - ml - mr, H - mt - mb
    teto, passo = _bonito(max(d["valor"] for d in dados) / 100)
    slot = pw / len(dados)
    larg = min(24.0, slot * 0.62)
    partes = [f'<svg class="grafico" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(rotulo_eixo)}" preserveAspectRatio="xMidYMid meet">']
    n_ticks = int(round(teto / passo))
    for k in range(n_ticks + 1):
        v = passo * k
        y = mt + ph - ph * v / teto
        partes.append(f'<line class="grade" x1="{ml}" x2="{W - mr}" y1="{y:.1f}" y2="{y:.1f}"/>')
        partes.append(f'<text class="eixo" x="{ml - 8}" y="{y + 4:.1f}" text-anchor="end">{escape(util.fmt_compacto(int(v * 100)))}</text>')
    maior = max(range(len(dados)), key=lambda i: dados[i]["valor"])
    pular = max(1, math.ceil(len(dados) / 12))
    for i, d in enumerate(dados):
        cx = ml + slot * (i + 0.5)
        h = ph * (d["valor"] / 100) / teto
        tip = _fmt_tip(util.mes_curto(d["mes"]), util.fmt_valor(d["valor"]), f"{d['qtd']} nota(s)")
        if i % pular == 0 or i == len(dados) - 1:
            partes.append(f'<text class="eixo" x="{cx:.1f}" y="{H - 12}" text-anchor="middle">{util.mes_curto(d["mes"])}</text>')
        if d["valor"] > 0:
            partes.append(f'<path class="coluna" d="{_topo_arredondado(cx - larg / 2, mt + ph - h, larg, h)}"/>')
            if i == maior or i == len(dados) - 1:   # rótulo seletivo: o maior e o último
                partes.append(f'<text class="valor" x="{cx:.1f}" y="{mt + ph - h - 6:.1f}" text-anchor="middle">{escape(util.fmt_compacto(d["valor"]))}</text>')
        # alvo de hover maior que a marca
        partes.append(f'<rect class="alvo" data-tip="{tip}" x="{cx - slot / 2:.1f}" y="{mt}" width="{slot:.1f}" height="{ph}"/>')
    partes.append(f'<line class="base" x1="{ml}" x2="{W - mr}" y1="{mt + ph}" y2="{mt + ph}"/></svg>')
    return "".join(partes)


def _arco(cx, cy, r_ext, r_int, a0, a1) -> str:
    def pt(r, a):
        return cx + r * math.cos(a), cy + r * math.sin(a)
    grande = 1 if (a1 - a0) > math.pi else 0
    x0, y0 = pt(r_ext, a0)
    x1, y1 = pt(r_ext, a1)
    x2, y2 = pt(r_int, a1)
    x3, y3 = pt(r_int, a0)
    return (f"M{x0:.2f},{y0:.2f} A{r_ext},{r_ext} 0 {grande} 1 {x1:.2f},{y1:.2f} L{x2:.2f},{y2:.2f} "
            f"A{r_int},{r_int} 0 {grande} 0 {x3:.2f},{y3:.2f} Z")


def rosca(fatias: list[dict], classes: list[str], centro_titulo: str, centro_valor: str, aria: str,
          valor_fmt=util.fmt_valor, chave_valor: str = "valor") -> str:
    """fatias: [{rotulo, <chave_valor>, pct}] na mesma ordem de `classes` (ex.: ['s1','s2',...,'so'])."""
    total = sum(f[chave_valor] for f in fatias)
    cx = cy = 100
    partes = [f'<svg class="rosca" viewBox="0 0 200 200" role="img" aria-label="{escape(aria)}">']
    if total <= 0:
        partes.append(f'<circle class="vazio" cx="{cx}" cy="{cy}" r="66"/>')
    else:
        ang = -math.pi / 2
        for f, cls in zip(fatias, classes, strict=False):
            if f[chave_valor] <= 0:
                continue
            frac = f[chave_valor] / total
            tip = _fmt_tip(f["rotulo"], valor_fmt(f[chave_valor]), util.fmt_pct(f["pct"]))
            if frac >= 0.9999:
                partes.append(f'<circle class="fatia anel {cls}" data-tip="{tip}" cx="{cx}" cy="{cy}" r="66"/>')
            else:
                fim = ang + frac * 2 * math.pi
                partes.append(f'<path class="fatia {cls}" data-tip="{tip}" d="{_arco(cx, cy, 80, 52, ang, fim)}"/>')
                ang = fim
    partes.append(f'<text class="centro-titulo" x="{cx}" y="{cy - 4}" text-anchor="middle">{escape(centro_titulo)}</text>')
    partes.append(f'<text class="centro-valor" x="{cx}" y="{cy + 16}" text-anchor="middle">{escape(centro_valor)}</text></svg>')
    return "".join(partes)


def classes_cores(fatias: list[dict]) -> list[str]:
    """s1..s5 em ordem fixa; 'Outros' sempre cinza (so)."""
    saida, k = [], 0
    for f in fatias:
        if f.get("outros"):
            saida.append("so")
        else:
            k += 1
            saida.append(f"s{k}")
    return saida
