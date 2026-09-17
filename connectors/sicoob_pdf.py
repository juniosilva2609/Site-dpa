"""Gera o PDF de extrato do Sicoob, inspirado no layout do internet
banking (modelo enviado pelo usuário: "Extrato de Conta Corrente"
impresso do SISBR/Internet Banking), mas montado diretamente com
reportlab (fontes padrão do PDF, sem embutimento) em vez de HTML +
Chromium — o Chromium sempre embute fontes subsetadas mesmo para nomes
de fonte "padrão" (Arial/Helvetica), o que gera arquivos grandes demais
para o limite de upload por chamada desta integração com o Google
Drive. Com reportlab e Helvetica (uma das 14 fontes padrão do PDF), o
arquivo fica bem mais leve, sem perder nenhum dado.

Importante: só usamos aqui campos que a API realmente devolve
(saldoAtual, saldoAnterior, saldoLimite, saldoBloqueado,
saldoBloqueioJudicial, transacoes). Seções do modelo original que
dependem de dados que essa API não fornece (juros/tarifas
provisionados, encargos a vencer, condições do cheque especial)
aparecem como "não disponível via API" — nunca preenchidas com valor
inventado.
"""

from datetime import date, datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

VERDE = colors.HexColor("#00995d")
VERDE_ESCURO = colors.HexColor("#1e7a4f")
VERMELHO = colors.HexColor("#c0392b")
CINZA = colors.HexColor("#666666")
FUNDO_SALDO = colors.HexColor("#f2f6f4")


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

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
    )

    titulo = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=16, textColor=VERDE)
    subtitulo = ParagraphStyle("subtitulo", fontName="Helvetica", fontSize=8, textColor=CINZA, leading=10)
    secao = ParagraphStyle("secao", fontName="Helvetica-Bold", fontSize=11, spaceBefore=10, spaceAfter=4)
    info = ParagraphStyle("info", fontName="Helvetica", fontSize=9, leading=13)
    hist = ParagraphStyle("hist", fontName="Helvetica", fontSize=9, leading=11)
    nota = ParagraphStyle("nota", fontName="Helvetica-Oblique", fontSize=7, textColor=colors.HexColor("#999999"))
    rodape = ParagraphStyle("rodape", fontName="Helvetica", fontSize=7, textColor=CINZA)

    elementos = [
        Paragraph("SICOOB", titulo),
        Paragraph(
            "SISTEMA DE COOPERATIVAS DE CRÉDITO DO BRASIL — PLATAFORMA DE SERVIÇOS "
            "FINANCEIROS DO SICOOB - SISBR",
            subtitulo,
        ),
        Spacer(1, 8),
        Paragraph(
            f"<b>Cooperativa:</b> {cooperativa} / {cooperativa_nome}<br/>"
            f"<b>Conta:</b> {conta} / {razao_social}<br/>"
            f"<b>Período:</b> {inicio.strftime('%d/%m/%Y')} - {fim.strftime('%d/%m/%Y')} &nbsp;&nbsp; "
            f"<b>Emitido em:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            info,
        ),
        Paragraph("HISTÓRICO DE MOVIMENTAÇÃO", secao),
    ]

    linhas = [["Data", "Documento", "Histórico", "Valor"]]
    estilos_linha = []
    row = 1
    for dia_iso, txs in dias:
        for t in txs:
            dia_fmt = datetime.fromisoformat(t["data"]).strftime("%d/%m")
            doc_num = t.get("numeroDocumento") or ""
            texto_hist = t.get("descricao", "")
            complemento = t.get("descInfComplementar", "")
            hist_html = f"{texto_hist}<br/><font size=7 color='#666666'>{complemento}</font>" if complemento else texto_hist
            valor = float(t["valor"])
            debito = t.get("tipo") == "DEBITO"
            valor_fmt = _fmt_moeda(-valor if debito else valor)
            linhas.append([dia_fmt, doc_num, Paragraph(hist_html, hist), valor_fmt])
            estilos_linha.append(("TEXTCOLOR", (3, row), (3, row), VERMELHO if debito else VERDE_ESCURO))
            row += 1

        saldo_dia = saldos_dia[dia_iso]
        dia_fmt = datetime.fromisoformat(dia_iso).strftime("%d/%m")
        linhas.append([dia_fmt, "", "SALDO DO DIA", _fmt_moeda(saldo_dia)])
        estilos_linha += [
            ("FONTNAME", (0, row), (-1, row), "Helvetica-Bold"),
            ("BACKGROUND", (0, row), (-1, row), FUNDO_SALDO),
            ("TEXTCOLOR", (3, row), (3, row), VERMELHO if saldo_dia < 0 else VERDE_ESCURO),
        ]
        row += 1

    linhas.append([inicio.strftime("%d/%m"), "", "SALDO ANTERIOR", _fmt_moeda(saldo_anterior)])
    estilos_linha += [
        ("FONTNAME", (0, row), (-1, row), "Helvetica-Bold"),
        ("BACKGROUND", (0, row), (-1, row), FUNDO_SALDO),
        ("TEXTCOLOR", (3, row), (3, row), VERMELHO if saldo_anterior < 0 else VERDE_ESCURO),
    ]

    tabela = Table(linhas, colWidths=[18 * mm, 28 * mm, 101 * mm, 27 * mm], repeatRows=1)
    tabela.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#999999")),
                ("ALIGN", (3, 0), (3, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 1), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
                *estilos_linha,
            ]
        )
    )
    elementos.append(tabela)

    elementos.append(Paragraph("RESUMO", secao))
    resumo = Table(
        [
            ["Saldo em conta:", _fmt_moeda(saldo_atual)],
            ["Cheque especial contratado:", _fmt_moeda(saldo_limite, False)],
            ["Juros vencidos provisionados:", "não disponível via API"],
            ["Tarifas vencidas provisionadas:", "não disponível via API"],
            ["Saldo disponível:", _fmt_moeda(saldo_disponivel)],
            ["Saldo bloqueado (cheques):", _fmt_moeda(saldo_bloqueado, False)],
            ["Saldo bloqueado (judicial):", _fmt_moeda(saldo_bloqueio_judicial, False)],
        ],
        colWidths=[80 * mm, 50 * mm],
    )
    resumo.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTNAME", (0, 4), (-1, 4), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    elementos.append(resumo)

    elementos.append(Paragraph("OUTRAS INFORMAÇÕES", secao))
    elementos.append(
        Paragraph(
            "Condições de cheque especial (vencimento, taxa, CET) e encargos a vencer não são "
            "fornecidos por este endpoint da API do Sicoob — não exibidos para não apresentar "
            "valor não confirmado.",
            nota,
        )
    )

    elementos.append(Paragraph("INFORMAÇÕES", secao))
    elementos.append(Paragraph("SAC: 0800 724 4420 / OUVIDORIA SICOOB: 08007250996", info))

    elementos.append(Spacer(1, 14))
    elementos.append(
        Paragraph(
            "Gerado automaticamente a partir da API oficial do Sicoob — DPA / Fechamento Bancário.",
            rodape,
        )
    )

    doc.build(elementos)
    return buf.getvalue()
