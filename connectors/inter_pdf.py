"""PDF do extrato do Inter no mesmo layout do PDF oficial do internet banking.

O PDF nativo da API (`/banking/v2/extrato/exportar`) embute fontes grandes
demais para o limite de upload da integração com o Google Drive, então o
documento é remontado com reportlab (fontes padrão, sem embutimento) a
partir dos dados da própria API, reproduzindo o PDF oficial conferido em
06/10/2026 contra o extrato da C3S de 09/2026 (85 lançamentos, mesmos
textos, ordem e saldos):

- Topo: "Solicitado em", razão social, CNPJ, agência/conta, período e o
  bloco de saldo atual (total, disponível, bloqueado) — `/banking/v2/saldo`
  sem data, igual ao banco, que mostra o saldo do momento da emissão.
- Dias em ordem crescente; dentro do dia, a ordem do `/extrato/completo`
  (lançamento mais recente primeiro). "Saldo por transação" é acumulado
  nessa ordem a partir do saldo do dia anterior ao período, e "Saldo do
  dia" é o saldo depois do último lançamento do dia.
- Texto do lançamento: `Título: "descrição"` sem acentos, onde a descrição
  é o trecho do `/extrato` depois do primeiro " - " (ex.: "PIX ENVIADO -
  Cp :13370835-CAJU" vira `Pix enviado: "Cp :13370835-CAJU"`).
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

MESES = (
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)
PRETO = colors.HexColor("#1a1a1a")
CINZA = colors.HexColor("#8a8a8a")
LINHA = colors.HexColor("#dddddd")
ZEBRA = colors.HexColor("#f5f5f5")
MARGEM = 17 * mm
LARGURA = A4[0] - 2 * MARGEM


class ExtratoInconsistente(ValueError):
    """Os dois endpoints de extrato do Inter não descrevem os mesmos lançamentos."""


def _norm(texto: str) -> str:
    sem_acento = "".join(
        ch for ch in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(ch)
    )
    return re.sub(r"\s+", " ", sem_acento).strip()


def _tokens(texto: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]{3,}", _norm(texto).lower()))


def _chave(dia: str, operacao: str, valor: str) -> tuple[str, str, int]:
    return dia, operacao, round(float(valor) * 100)


def texto_lancamento(simples: dict, completo: dict) -> str:
    titulo = _norm(simples.get("titulo", ""))
    prefixo, separador, resto = (simples.get("descricao") or "").partition(" - ")
    if not separador:
        prefixo, resto = "", prefixo
    prefixo, resto = _norm(prefixo), _norm(resto)
    if not resto:
        return _norm(f"{titulo} {completo.get('descricao', '')}")
    if prefixo and prefixo.upper() != resto.upper() and prefixo.upper().endswith(resto.upper()):
        return resto
    return f'{titulo}: "{resto}"'


def _afinidade(simples: dict, completo: dict) -> int:
    detalhes = completo.get("detalhes") or {}
    nosso_numero = detalhes.get("nossoNumero")
    if nosso_numero and nosso_numero in (simples.get("descricao") or ""):
        return 1000
    nomes = " ".join(
        str(detalhes.get(campo, ""))
        for campo in ("nomeRecebedor", "nomePagador", "detalheDescricao", "nomeDestinatario")
    )
    return len(_tokens(simples.get("descricao", "")) & _tokens(f"{completo.get('descricao', '')} {nomes}"))


def montar_lancamentos(simples: list[dict], completo: list[dict]) -> list[dict]:
    """Junta `/extrato` (texto que o banco exibe) com `/extrato/completo`
    (ordem que o banco exibe) e devolve os lançamentos na ordem do PDF
    oficial, cada um com `data`, `texto` e `valor` (negativo = débito)."""
    por_chave: dict[tuple, list[dict]] = defaultdict(list)
    for s in simples:
        por_chave[_chave(s["dataEntrada"], s["tipoOperacao"], s["valor"])].append(s)

    completo_por_chave: dict[tuple, list[int]] = defaultdict(list)
    for i, c in enumerate(completo):
        completo_por_chave[_chave(c["dataTransacao"], c["tipoOperacao"], c["valor"])].append(i)

    if {k: len(v) for k, v in por_chave.items()} != {k: len(v) for k, v in completo_por_chave.items()}:
        raise ExtratoInconsistente("/extrato e /extrato/completo devolveram lançamentos diferentes")

    par_de: dict[int, dict] = {}
    for chave, indices in completo_por_chave.items():
        candidatos = sorted(
            ((_afinidade(s, completo[i]), si, i) for si, s in enumerate(por_chave[chave]) for i in indices),
            key=lambda item: -item[0],
        )
        usados_s, usados_c = set(), set()
        for _, si, i in candidatos:
            if si in usados_s or i in usados_c:
                continue
            par_de[i] = por_chave[chave][si]
            usados_s.add(si)
            usados_c.add(i)

    ordem = sorted(range(len(completo)), key=lambda i: completo[i]["dataTransacao"])
    lancamentos = []
    for i in ordem:
        c = completo[i]
        valor = float(c["valor"])
        lancamentos.append(
            {
                "data": date.fromisoformat(c["dataTransacao"]),
                "texto": texto_lancamento(par_de[i], c),
                "valor": valor if c["tipoOperacao"] == "C" else -valor,
            }
        )
    return lancamentos


def com_saldos(lancamentos: list[dict], saldo_inicial: float) -> list[dict]:
    saldo = saldo_inicial
    resultado = []
    for lanc in lancamentos:
        saldo = round(saldo + lanc["valor"], 2)
        resultado.append({**lanc, "saldo": saldo})
    return resultado


def _moeda(valor: float) -> str:
    texto = f"{abs(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{'-' if valor < 0 else ''}R$ {texto}"


def _data_extenso(dia: date) -> str:
    return f"{dia.day} de {MESES[dia.month - 1]} de {dia.year}"


def _rodape(canvas, doc) -> None:
    canvas.saveState()
    y = 24 * mm
    canvas.setStrokeColor(LINHA)
    canvas.setLineWidth(0.5)
    canvas.line(MARGEM, y, A4[0] - MARGEM, y)
    canvas.setFillColor(PRETO)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(MARGEM, y - 5 * mm, "Fale com a gente")
    base = y - 9 * mm
    itens = [
        (MARGEM, "SAC: ", "0800 940 9999", " (opção 09)"),
        (MARGEM + 66 * mm, "Ouvidoria: ", "0800 940 7772", ""),
        (MARGEM + 116 * mm, "Deficiência de fala e audição: ", "0800 979 7099", ""),
    ]
    for x, rotulo, numero, extra in itens:
        canvas.setFont("Helvetica", 7)
        canvas.drawString(x, base, rotulo)
        x += canvas.stringWidth(rotulo, "Helvetica", 7)
        canvas.setFont("Helvetica-Bold", 7)
        canvas.drawString(x, base, numero)
        if extra:
            x += canvas.stringWidth(numero, "Helvetica-Bold", 7)
            canvas.setFont("Helvetica", 5)
            canvas.drawString(x, base, extra)
    canvas.setFillColor(CINZA)
    canvas.setFont("Helvetica", 5)
    canvas.drawRightString(
        A4[0] - MARGEM, 8 * mm, "Gerado a partir da API oficial do Banco Inter (extrato, extrato completo e saldo)"
    )
    canvas.restoreState()


def gerar_pdf(
    lancamentos: list[dict],
    saldo_inicial: float,
    saldo_atual: dict,
    conta: str,
    agencia: str,
    razao_social: str,
    cnpj: str,
    inicio: date,
    fim: date,
    solicitado_em: datetime,
) -> bytes:
    linhas_saldo = com_saldos(lancamentos, saldo_inicial)
    bloqueado = sum(
        float(saldo_atual.get(campo, 0) or 0)
        for campo in ("bloqueadoCheque", "bloqueadoJudicialmente", "bloqueadoAdministrativo")
    )
    disponivel = float(saldo_atual.get("disponivel", 0) or 0)

    texto = ParagraphStyle("texto", fontName="Helvetica", fontSize=8, leading=11, textColor=PRETO)
    empresa = ParagraphStyle("empresa", parent=texto, fontName="Helvetica-Bold", fontSize=9)
    rotulo = ParagraphStyle("rotulo", parent=texto, fontSize=7, leading=9, textColor=CINZA)
    rotulo_preto = ParagraphStyle("rotulo_preto", parent=rotulo, textColor=PRETO)
    valor_destaque = ParagraphStyle("valor_destaque", parent=texto, fontName="Helvetica-Bold", fontSize=8.5)
    nota = ParagraphStyle("nota", parent=texto, fontSize=5.5, leading=7)
    dia_estilo = ParagraphStyle("dia", parent=texto, fontSize=8)
    lanc_estilo = ParagraphStyle("lanc", parent=texto, fontSize=8, leading=10)
    cabecalho_col = ParagraphStyle("col", parent=texto, fontSize=8, textColor=CINZA, alignment=2)
    valor_estilo = ParagraphStyle("valor", parent=texto, fontName="Helvetica-Bold", fontSize=8, alignment=2)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=14 * mm,
        bottomMargin=30 * mm,
        leftMargin=MARGEM,
        rightMargin=MARGEM,
        title=f"Extrato {inicio.strftime('%d-%m-%Y')} a {fim.strftime('%d-%m-%Y')}",
    )

    logo = ParagraphStyle("logo", parent=texto, fontName="Helvetica-Bold", fontSize=22, leading=24)
    carimbo = ParagraphStyle("carimbo", parent=texto, fontSize=7, textColor=CINZA, alignment=2)
    topo = Table(
        [[Paragraph("inter", logo),
          Paragraph(f"Solicitado em: {solicitado_em.strftime('%d/%m/%Y - %Hh%M')}", carimbo)]],
        colWidths=[LARGURA / 2, LARGURA / 2],
    )
    topo.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    elementos = [
        topo,
        Spacer(1, 22),
        Paragraph(_norm(razao_social).upper(), empresa),
        Spacer(1, 3),
        Paragraph(
            f"CPF/CNPJ: <b>{cnpj}</b>, Instituição: <b>Banco Inter</b>, "
            f"Agência: <b>{agencia}</b>, Conta: <b>{conta}</b>",
            texto,
        ),
        Spacer(1, 3),
        Paragraph(f"Período: <b>{inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}</b>", texto),
        Spacer(1, 6),
    ]

    bloco_saldo = Table(
        [
            [
                [Paragraph("Saldo total", rotulo_preto), Paragraph(_moeda(disponivel + bloqueado), valor_destaque),
                 Paragraph("(bloqueado + disponível)", nota)],
                [Paragraph("Saldo disponível:", rotulo), Paragraph(_moeda(disponivel), valor_destaque)],
                [Paragraph("Saldo bloqueado:", rotulo), Paragraph(_moeda(bloqueado), valor_destaque)],
            ]
        ],
        colWidths=[35 * mm, 35 * mm, LARGURA - 70 * mm],
    )
    bloco_saldo.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 0.5, LINHA),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, LINHA),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    elementos += [bloco_saldo, Spacer(1, 16)]

    larguras = [LARGURA - 70 * mm, 30 * mm, 40 * mm]
    if not linhas_saldo:
        elementos.append(Paragraph("Nenhum lançamento no período.", texto))

    por_dia: dict[date, list[dict]] = defaultdict(list)
    for linha in linhas_saldo:
        por_dia[linha["data"]].append(linha)

    for n, (dia, itens) in enumerate(por_dia.items()):
        cabecalho = Paragraph(
            f"<b>{_data_extenso(dia)}</b> Saldo do dia: <b>{_moeda(itens[-1]['saldo'])}</b>", dia_estilo
        )
        linhas = [
            [cabecalho, Paragraph("Valor", cabecalho_col) if n == 0 else "",
             Paragraph("Saldo por transação", cabecalho_col) if n == 0 else ""]
        ]
        estilos = [
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#c8c8c8")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, 0), 6),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 9),
            ("LEFTPADDING", (0, 0), (0, -1), 3),
            ("TOPPADDING", (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ]
        for j, item in enumerate(itens, start=1):
            linhas.append(
                [Paragraph(item["texto"], lanc_estilo), Paragraph(_moeda(item["valor"]), valor_estilo),
                 Paragraph(_moeda(item["saldo"]), valor_estilo)]
            )
            if j % 2 == 0:
                estilos.append(("BACKGROUND", (0, j), (-1, j), ZEBRA))
        tabela = Table(linhas, colWidths=larguras)
        tabela.setStyle(TableStyle(estilos))
        elementos += [tabela, Spacer(1, 10)]

    doc.build(elementos, onFirstPage=_rodape, onLaterPages=_rodape)
    return buf.getvalue()
