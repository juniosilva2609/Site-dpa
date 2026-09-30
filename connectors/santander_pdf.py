"""Gera um PDF alternativo (leve) do extrato do Santander.

Isto NÃO é o extrato oficial do banco. A API "Saldo e Extrato" do Santander
não oferece exportação nativa em PDF/OFX/Excel — só JSON (mesma situação do
Inter e do Sicoob) — por isso o PDF é montado aqui com reportlab (fontes
padrão, sem embutimento), a partir das mesmas listas de lançamentos
efetivos/provisionados já buscadas por `connectors/santander.py`.

Combina lançamentos efetivos e provisionados (a API do Santander devolve os
dois separadamente para conta própria) e marca os provisionados como tal,
já que eles ainda não foram compensados e podem mudar.
"""

from datetime import date, datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

VERMELHO_SANTANDER = colors.HexColor("#ec0000")
VERDE = colors.HexColor("#1e7a4f")
VERMELHO = colors.HexColor("#c0392b")
CINZA = colors.HexColor("#666666")


def _fmt_moeda(valor: float, credito: bool) -> str:
    texto = f"{abs(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    sufixo = "C" if credito else "D"
    return f"R$ {texto}{sufixo}"


def _fmt_data(data_br: str) -> str:
    """Já vem como DD/MM/AAAA da API; só valida e devolve, ou "-" se vazio."""
    try:
        datetime.strptime(data_br, "%d/%m/%Y")
        return data_br
    except (ValueError, TypeError):
        return data_br or "-"


def gerar_pdf(
    transacoes: list[dict],
    conta: str,
    agencia: str,
    razao_social: str,
    inicio: date,
    fim: date,
) -> bytes:
    total_creditos = sum(t["valor"] for t in transacoes if t["credito"])
    total_debitos = sum(t["valor"] for t in transacoes if not t["credito"])

    def chave_ordenacao(t: dict):
        try:
            return datetime.strptime(t["data"], "%d/%m/%Y")
        except (ValueError, TypeError):
            return datetime.min

    ordenadas = sorted(transacoes, key=chave_ordenacao, reverse=True)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
    )

    titulo = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=16, textColor=VERMELHO_SANTANDER)
    subtitulo = ParagraphStyle("subtitulo", fontName="Helvetica", fontSize=8, textColor=CINZA, leading=10)
    secao = ParagraphStyle("secao", fontName="Helvetica-Bold", fontSize=11, spaceBefore=10, spaceAfter=4)
    info = ParagraphStyle("info", fontName="Helvetica", fontSize=9, leading=13)
    nota = ParagraphStyle("nota", fontName="Helvetica-Oblique", fontSize=7, textColor=colors.HexColor("#999999"))
    rodape = ParagraphStyle("rodape", fontName="Helvetica", fontSize=7, textColor=CINZA)

    elementos = [
        Paragraph("SANTANDER", titulo),
        Paragraph(
            "EXTRATO DE CONTA CORRENTE — documento gerado por conector próprio a partir "
            "da API oficial (não é o extrato nativo do banco)",
            subtitulo,
        ),
        Spacer(1, 8),
        Paragraph(
            f"<b>Agência:</b> {agencia} &nbsp;&nbsp; <b>Conta:</b> {conta} / {razao_social}<br/>"
            f"<b>Período:</b> {inicio.strftime('%d/%m/%Y')} - {fim.strftime('%d/%m/%Y')} &nbsp;&nbsp; "
            f"<b>Emitido em:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
            info,
        ),
        Paragraph("HISTÓRICO DE MOVIMENTAÇÃO", secao),
    ]

    linhas = [["Data", "Histórico", "Valor"]]
    estilos_linha = []
    for i, t in enumerate(ordenadas, start=1):
        hist = f"{t['descricao']}"
        if t["complemento"]:
            hist += f"<br/><font size=7 color='#666666'>{t['complemento']}</font>"
        if t["provisionado"]:
            hist += " <font size=7 color='#999999'>[PROVISIONADO]</font>"
        valor_fmt = _fmt_moeda(t["valor"], t["credito"])
        linhas.append([_fmt_data(t["data"]), Paragraph(hist, info), valor_fmt])
        estilos_linha.append(("TEXTCOLOR", (2, i), (2, i), VERDE if t["credito"] else VERMELHO))

    tabela = Table(linhas, colWidths=[25 * mm, 122 * mm, 27 * mm], repeatRows=1)
    tabela.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#999999")),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 1), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
                *estilos_linha,
            ]
        )
    )
    elementos.append(tabela)

    elementos.append(Paragraph("RESUMO DO PERÍODO", secao))
    resumo = Table(
        [
            ["Total de créditos:", _fmt_moeda(total_creditos, True)],
            ["Total de débitos:", _fmt_moeda(total_debitos, False)],
            [
                "Movimentação líquida:",
                _fmt_moeda(abs(total_creditos - total_debitos), total_creditos >= total_debitos),
            ],
        ],
        colWidths=[60 * mm, 40 * mm],
    )
    resumo.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("TEXTCOLOR", (1, 0), (1, 0), VERDE),
                ("TEXTCOLOR", (1, 1), (1, 1), VERMELHO),
            ]
        )
    )
    elementos.append(resumo)

    elementos.append(Paragraph("OUTRAS INFORMAÇÕES", secao))
    elementos.append(
        Paragraph(
            "Saldo em conta não é consultado por este conector (só extrato) — por isso não é "
            "exibido aqui. Lançamentos marcados [PROVISIONADO] ainda não foram compensados e "
            "podem mudar ou ser cancelados. Não há identificador único por lançamento nesta "
            "API para contas próprias do Santander; a ordem/agrupamento acima é a devolvida "
            "pelo banco.",
            nota,
        )
    )

    elementos.append(Spacer(1, 14))
    elementos.append(
        Paragraph(
            "Gerado automaticamente a partir da API oficial do Santander — DPA / Fechamento "
            "Bancário. Documento NÃO é o extrato oficial emitido pelo banco.",
            rodape,
        )
    )

    doc.build(elementos)
    return buf.getvalue()
