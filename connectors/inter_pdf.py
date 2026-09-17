"""Gera um PDF alternativo (leve) do extrato do Inter.

Isto NÃO é o PDF oficial do banco. O Inter tem exportação nativa de PDF
(`/banking/v2/extrato/exportar`), mas esse PDF embute fontes customizadas
e fica grande demais para o limite de upload desta integração com o
Google Drive. Este módulo monta o PDF diretamente com reportlab, usando
apenas as 14 fontes padrão do PDF (Helvetica) — que não precisam ser
embutidas no arquivo — a partir do mesmo JSON de transações
(`/banking/v2/extrato`), resultando num arquivo bem mais leve.

Usa somente os campos que a API de extrato do Inter realmente devolve
(dataEntrada, tipoTransacao, tipoOperacao, valor, titulo, descricao) —
não existe saldo nesse endpoint, então nenhum valor de saldo é exibido
ou inventado.
"""

from datetime import date, datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import ParagraphStyle

LARANJA = colors.HexColor("#ff7a00")
VERDE = colors.HexColor("#1e7a4f")
VERMELHO = colors.HexColor("#c0392b")
CINZA = colors.HexColor("#666666")


def _fmt_moeda(valor: float, credito: bool) -> str:
    texto = f"{abs(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    sufixo = "C" if credito else "D"
    return f"R$ {texto}{sufixo}"


def gerar_pdf(
    transacoes: list[dict],
    conta: str,
    agencia: str,
    razao_social: str,
    inicio: date,
    fim: date,
) -> bytes:
    total_creditos = sum(float(t["valor"]) for t in transacoes if t.get("tipoOperacao") == "C")
    total_debitos = sum(float(t["valor"]) for t in transacoes if t.get("tipoOperacao") == "D")
    ordenadas = sorted(transacoes, key=lambda t: t["dataEntrada"], reverse=True)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
    )

    titulo = ParagraphStyle("titulo", fontName="Helvetica-Bold", fontSize=16, textColor=LARANJA)
    subtitulo = ParagraphStyle("subtitulo", fontName="Helvetica", fontSize=8, textColor=CINZA, leading=10)
    secao = ParagraphStyle("secao", fontName="Helvetica-Bold", fontSize=11, spaceBefore=10, spaceAfter=4)
    info = ParagraphStyle("info", fontName="Helvetica", fontSize=9, leading=13)
    nota = ParagraphStyle("nota", fontName="Helvetica-Oblique", fontSize=7, textColor=colors.HexColor("#999999"))
    rodape = ParagraphStyle("rodape", fontName="Helvetica", fontSize=7, textColor=CINZA)

    elementos = [
        Paragraph("BANCO INTER", titulo),
        Paragraph(
            "EXTRATO DE CONTA CORRENTE — documento gerado por conector próprio a partir "
            "da API oficial (não é o PDF nativo do banco)",
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

    linhas = [["Data", "Tipo", "Histórico", "Valor"]]
    estilos_linha = []
    for i, t in enumerate(ordenadas, start=1):
        dia = datetime.strptime(t["dataEntrada"], "%Y-%m-%d").strftime("%d/%m/%Y")
        credito = t.get("tipoOperacao") == "C"
        valor_fmt = _fmt_moeda(float(t.get("valor", 0)), credito)
        hist = f"{t.get('titulo', '')}<br/><font size=7 color='#666666'>{t.get('descricao', '')}</font>"
        linhas.append([dia, t.get("tipoTransacao", ""), Paragraph(hist, info), valor_fmt])
        estilos_linha.append(("TEXTCOLOR", (3, i), (3, i), VERDE if credito else VERMELHO))

    tabela = Table(linhas, colWidths=[22 * mm, 30 * mm, 95 * mm, 27 * mm], repeatRows=1)
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
            "Saldo em conta não é fornecido pelo endpoint de extrato da API do Inter "
            "(/banking/v2/extrato) — por isso não é exibido aqui. O PDF nativo do banco "
            "(com saldo) pode ser obtido diretamente pelo app/site do Inter quando necessário.",
            nota,
        )
    )

    elementos.append(Spacer(1, 14))
    elementos.append(
        Paragraph(
            "Gerado automaticamente a partir da API oficial do Banco Inter — DPA / Fechamento "
            "Bancário. Documento NÃO é o extrato oficial emitido pelo banco.",
            rodape,
        )
    )

    doc.build(elementos)
    return buf.getvalue()
