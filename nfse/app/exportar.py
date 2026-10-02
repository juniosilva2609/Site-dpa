# -*- coding: utf-8 -*-
"""Exportação dos relatórios: CSV (abre direto no Excel em português) e PDF com a marca da JL."""

import csv
import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import util
from .fiscal import danfse  # noqa: F401 -- registra as fontes Microsoft Sans Serif/Arial (com acentos)

_LOGO = Path(__file__).parent / "static" / "img" / "jl-mono.png"
_OURO = colors.HexColor("#b8892b")


def reais(centavos: int | None) -> str:
    """1500,00 (sem R$, vírgula decimal): coluna numérica do Excel."""
    return "" if centavos is None else f"{centavos / 100:.2f}".replace(".", ",")


def csv_bytes(cabecalho: list[str], linhas: list[list]) -> bytes:
    """UTF-8 com BOM e ';' como separador: o Excel brasileiro abre com acentos e colunas certos."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(cabecalho)
    for linha in linhas:
        w.writerow([("'" + c if isinstance(c, str) and c[:1] in "=+-@" and not c[1:2].isdigit() else c) for c in linha])  # anti injeção de fórmula
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def pdf_relatorio(titulo: str, subtitulo: str, kpis: list[tuple[str, str]], tabelas: list[dict], paisagem: bool = False) -> bytes:
    """tabelas: [{titulo, cabecalho: [...], linhas: [[...]], larguras: [mm...]|None, direita: [índices numéricos]}]"""
    tam = landscape(A4) if paisagem else A4
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=tam, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=14 * mm,
                            title=titulo, author="JL Transportes Executivos Ltda")
    h1 = ParagraphStyle("h1", fontName="Arial-Bold", fontSize=15, leading=18, textColor=colors.white)
    sub = ParagraphStyle("sub", fontName="MSSansSerif", fontSize=9, leading=11, textColor=colors.HexColor("#d8c28a"))
    h2 = ParagraphStyle("h2", fontName="Arial-Bold", fontSize=11, leading=14, spaceBefore=10, spaceAfter=4)
    cel = ParagraphStyle("cel", fontName="MSSansSerif", fontSize=8, leading=9.5)
    kpi_est = ParagraphStyle("kpi", fontName="MSSansSerif", fontSize=8, leading=15)
    larg_util = tam[0] - 28 * mm
    # faixa preta com a marca
    logo = Image(str(_LOGO), width=18 * mm, height=18 * mm * 311 / 360)
    faixa = Table([[logo, [Paragraph("JL Transportes Executivos Ltda", h1), Paragraph(f"{titulo} · {subtitulo}", sub)]]],
                  colWidths=[24 * mm, larg_util - 24 * mm])
    faixa.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0b0a09")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("LINEBELOW", (0, 0), (-1, -1), 1.5, _OURO), ("LEFTPADDING", (0, 0), (-1, -1), 6),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    el = [faixa, Spacer(1, 6)]
    if kpis:
        n = len(kpis)
        t = Table([[Paragraph(f"<font size=7 color='#666666'>{k}</font><br/><font name='Arial-Bold' size=12>{v}</font>", kpi_est) for k, v in kpis]],
                  colWidths=[larg_util / n] * n)
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")), ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        el += [t, Spacer(1, 4)]
    for tb in tabelas:
        el.append(Paragraph(tb["titulo"], h2))
        linhas = [[Paragraph(f"<font name='Arial-Bold'>{c}</font>", cel) for c in tb["cabecalho"]]]
        for linha in tb["linhas"]:
            linhas.append([Paragraph(str(c).replace("&", "&amp;").replace("<", "&lt;"), cel) for c in linha])
        if not tb["linhas"]:
            linhas.append([Paragraph("Nenhum registro.", cel)] + [""] * (len(tb["cabecalho"]) - 1))
        larg = [x * mm for x in tb["larguras"]] if tb.get("larguras") else None
        t = Table(linhas, colWidths=larg, repeatRows=1)
        est = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efe6cf")), ("LINEBELOW", (0, 0), (-1, 0), 0.8, _OURO),
               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f5ef")]), ("VALIGN", (0, 0), (-1, -1), "TOP"),
               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor("#cccccc"))]
        for i in tb.get("direita", []):
            est.append(("ALIGN", (i, 0), (i, -1), "RIGHT"))
        t.setStyle(TableStyle(est))
        el.append(t)

    def rodape(c, d):
        c.saveState()
        c.setFont("MSSansSerif", 7)
        c.setFillColor(colors.HexColor("#777777"))
        c.drawString(14 * mm, 8 * mm, f"Gerado em {util.agora().strftime('%d/%m/%Y %H:%M')} · NFS-e Automática")
        c.drawRightString(tam[0] - 14 * mm, 8 * mm, f"Página {d.page}")
        c.restoreState()
    doc.build(el, onFirstPage=rodape, onLaterPages=rodape)
    return buf.getvalue()
