# -*- coding: utf-8 -*-
"""DANFSe layout v1.0 -- reprodução do PDF emitido pelo Portal Nacional/Prefeitura de Belo Horizonte
(modelo da JL Transportes, NFS-e 480 de 16/07/2026), medida diretamente nas coordenadas vetoriais do
PDF original: fonte única Microsoft Sans Serif (negrito SIMULADO por contorno, como o PDFsharp do
original: modo de texto 2, traço 0,14/0,16/0,18 pt), grade de 4 colunas de 141,7 pt, filetes de 0,5 pt
entre blocos e moldura de 1 pt.

Lê só o XML oficial da NFS-e (nunca dados internos). Código sem mapeamento conhecido levanta
`DanfseIndisponivel` em vez de arriscar um texto errado."""

import io
import os

from lxml import etree
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas as _canvas_mod

from . import danfse as d
from . import xmlseguro

_DIR = os.path.dirname(__file__)
_LOGO = os.path.join(_DIR, "assets", "nfse_logo.png")
_BRASAO_BH = os.path.join(_DIR, "assets", "brasao_belo_horizonte.png")
_FONTE = d._FONTE_CONTEUDO
W, H = 595.0, 842.0
X = [14.2, 155.9, 297.6, 439.4]       # colunas
COL = 141.7
ESQ, DIR = 10.8, 577.7                 # extensão dos filetes
_ASC = 0.7875                          # topo do glifo -> linha de base (medido no original)
_COD_BH = "3106200"

_OP_SIMP = {"1": "Não Optante", "2": "Optante - Microempreendedor Individual (MEI)",
            "3": "Optante - Microempresa ou Empresa de Pequeno Porte (ME/EPP)"}
_REG_ESP = {"0": "Nenhum", "1": "Ato Cooperado (Cooperativa)", "2": "Estimativa", "3": "Microempresa Municipal",
            "4": "Notário ou Registrador", "5": "Profissional Autônomo", "6": "Sociedade de Profissionais"}
_TP_IMUN = {"0": "Imunidade (tipo não informado na NF-e)", "1": "Patrimônio, renda ou serviços, uns dos outros (CF88, Art 150, VI, a)",
            "2": "Entidades religiosas e templos de qualquer culto (CF88, Art 150, VI, b)",
            "3": "Patrimônio, renda ou serviços dos partidos políticos (CF88, Art 150, VI, c)",
            "4": "Livros, jornais, periódicos e o papel destinado a sua impressão (CF88, Art 150, VI, d)",
            "5": "Fonogramas e videofonogramas musicais produzidos no Brasil (CF88, Art 150, VI, e)"}


class _Pagina:
    def __init__(self, c):
        self.c = c

    def y(self, top: float, tamanho: float) -> float:
        return H - (top + _ASC * tamanho)

    def texto(self, x, top, s, tamanho=8, negrito=False, largura=None, centro=None, cor=colors.black):
        s = s if s else "-"
        if largura:
            s = d._ajustar(s, largura, _FONTE, tamanho)
        traco = {7: 0.14, 8: 0.16, 9: 0.18}.get(int(tamanho), 0.14)
        c = self.c
        c.saveState()   # Tr/Tc fazem parte do estado gráfico: q ... Q impede o negrito de vazar para o próximo texto
        c.setFillColor(cor)
        c.setStrokeColor(cor)
        t = c.beginText()
        # Tr/Tc persistem entre textos no PDF: definir SEMPRE, senão o negrito "vaza" para o texto seguinte.
        c.setLineWidth(traco if negrito else 0.5)
        t.setTextRenderMode(2 if negrito else 0)
        t.setCharSpace(traco if negrito else 0)
        largura_txt = pdfmetrics.stringWidth(s, _FONTE, tamanho) + (traco * len(s) if negrito else 0)
        if centro is not None:
            x = centro - largura_txt / 2
        t.setTextOrigin(x, self.y(top, tamanho))
        t.setFont(_FONTE, tamanho)
        t.textOut(s)
        c.drawText(t)
        c.restoreState()

    def filete(self, top):
        self.c.setLineWidth(0.5)
        self.c.setStrokeColor(colors.black)
        self.c.line(ESQ, H - top, DIR, H - top)

    def rotulo(self, col, top, s):
        self.texto(X[col], top, s, 7, True)

    def valor(self, col, top, s, cols=1):
        self.texto(X[col], top, s, 8, largura=COL * cols - 4)

    def campo(self, col, top, rotulo, valor, cols=1):
        self.rotulo(col, top, rotulo)
        self.valor(col, top + 8.1, valor, cols)

    def titulo(self, top, s):
        self.texto(X[0], top, s, 8, True)


def _linhas(texto: str, largura: float, max_linhas: int | None = None) -> list[str]:
    return d._quebrar(texto, largura, _FONTE, 8, max_linhas)


def _limitar66(texto: str | None) -> str:
    """Corte do DANFSe v1.0 para o código de tributação: mais de 66 caracteres -> 63 + "..." (idêntico ao
    original: '004 - Outros serviços de transporte municipal de passageiros po...')."""
    t = " ".join((texto or "").split())
    return t[:63] + "..." if len(t) > 66 else t


def _uf_emit(inf) -> str:
    return d._t(inf, "emit/enderNac/UF") or ""


def _municipio_uf(nome: str | None, uf: str) -> str:
    return f"{nome} - {uf}" if nome and uf else (nome or "-")


def _tomador_cidade(toma) -> str:
    cmun = d._t(toma, "end/endNac/cMun")
    achado = d.nome_municipio_ibge(cmun) if cmun else None
    if achado:
        return f"{achado[0]} - {achado[1]}"
    return cmun or "-"


def _cep(v: str | None) -> str:
    """NNNNN-NNN (formato do DANFSe v1.0 da prefeitura; o motor v2 usa NN.NNN-NNN)."""
    dig = "".join(ch for ch in (v or "") if ch.isdigit())
    return f"{dig[:5]}-{dig[5:]}" if len(dig) == 8 else (v or "-")


def _fmt_aliq(v):
    try:
        return f"{float(v):.2f}%".replace(".", ",")
    except (TypeError, ValueError):
        return "-"


def gerar_danfse_pdf(xml_nfse: str, marca_dagua: str | None = None) -> bytes:
    if not xml_nfse:
        raise d.DanfseIndisponivel("Essa NFS-e não tem o XML oficial salvo -- não dá para montar o DANFSe.")
    try:
        raiz = xmlseguro.parse(xml_nfse)
    except (etree.XMLSyntaxError, ValueError) as e:
        raise d.DanfseIndisponivel(f"XML da NFS-e inválido: {e}") from e
    inf = raiz if raiz.tag.endswith("infNFSe") else raiz.find("n:infNFSe", namespaces=d._NS)
    if inf is None:
        raise d.DanfseIndisponivel("XML não tem o elemento infNFSe esperado.")
    dps = inf.find("n:DPS/n:infDPS", namespaces=d._NS)
    if dps is None:
        raise d.DanfseIndisponivel("XML não tem o elemento DPS/infDPS esperado.")
    t = d._t
    chave = inf.get("Id", "").removeprefix("NFS")
    homolog = t(dps, "tpAmb") == "2"
    prest = dps.find("n:prest", namespaces=d._NS)
    toma = dps.find("n:toma", namespaces=d._NS)
    serv = dps.find("n:serv/n:cServ", namespaces=d._NS)
    trib = dps.find("n:valores/n:trib/n:tribMun", namespaces=d._NS)
    uf = _uf_emit(inf)
    cod_emissor = t(dps, "cLocEmi") or t(inf, "emit/enderNac/cMun") or ""

    buf = io.BytesIO()
    c = _canvas_mod.Canvas(buf, pagesize=(W, H))
    p = _Pagina(c)

    # moldura
    c.setLineWidth(1)
    c.rect(5, 5, 585, 832, fill=0, stroke=1)

    # ---- cabeçalho
    try:
        c.drawImage(ImageReader(_LOGO), 14.17, H - 12.5 - 22.68, 113.39, 22.68, mask="auto")
    except Exception:  # noqa: BLE001
        pass
    largura_t = pdfmetrics.stringWidth("DANFSe v1.0", _FONTE, 9) + 0.18 * 11
    centro = 223.27 + largura_t / 2
    p.texto(0, 15.7, "DANFSe v1.0", 9, True, centro=centro)
    p.texto(0, 25.9, "Documento Auxiliar da NFS-e", 9, True, centro=centro)
    if homolog:
        p.texto(0, 34.2, "NFS-e SEM VALIDADE JURÍDICA", 6, True, centro=centro, cor=colors.red)
    municipio = t(inf, "xLocEmi") or "-"
    x_pref = 439.37
    if cod_emissor == _COD_BH:
        try:
            c.drawImage(ImageReader(_BRASAO_BH), 402.57, H - 8.83 - 30, 30, 30, mask="auto")
        except Exception:  # noqa: BLE001
            pass
    linhas_pref = _linhas(f"Prefeitura Municipal de {municipio}", 135)
    for k, ln in enumerate(linhas_pref[:2]):
        p.texto(x_pref, 9.6 + 9.05 * k, ln, 8)
    if cod_emissor == _COD_BH:
        p.texto(x_pref, 9.6 + 9.05 * (len(linhas_pref[:2])) - 0.2 + 0.0, "Secretaria Municipal de Fazenda - SMFA", 6)
    p.filete(41.2)

    # ---- identificação
    p.texto(X[0], 46.6, "Chave de Acesso da NFS-e", 7, True)
    p.texto(X[0], 54.7, chave, 8)
    p.campo(0, 67.9, "Número da NFS-e", t(inf, "nNFSe"))
    p.campo(1, 67.9, "Competência da NFS-e", d._data_br(t(dps, "dCompet")))
    p.campo(2, 67.9, "Data e Hora da emissão da NFS-e", d._data_hora_br(t(inf, "dhProc")))
    p.campo(0, 89.1, "Número da DPS", t(dps, "nDPS"))
    p.campo(1, 89.1, "Série da DPS", t(dps, "serie"))
    p.campo(2, 89.1, "Data e Hora da emissão da DPS", d._data_hora_br(t(dps, "dhEmi")))
    c.drawImage(d._qrcode_imagem(chave), 481.83, H - 46.0 - 50, 50, 50, mask="auto")
    for k, ln in enumerate(["A autenticidade desta NFS-e pode ser verificada",
                            "pela leitura deste código QR ou pela consulta da",
                            "chave de acesso no portal nacional da NFS-e"]):
        p.texto(X[3], 98.9 + 6.8 * k, ln, 6)
    p.filete(123.0)

    # ---- emitente / prestador
    emit_nome = {"1": "Prestador do Serviço", "2": "Tomador do Serviço", "3": "Intermediário do Serviço"}
    tp_emit = t(dps, "tpEmit")
    if tp_emit not in emit_nome:
        raise d.DanfseIndisponivel(f"Divergência de dados no DANFSe -- tpEmit {tp_emit!r} sem mapeamento.")
    p.titulo(124.3, "EMITENTE DA NFS-e")
    p.texto(X[0], 133.4, emit_nome[tp_emit], 8)
    p.campo(1, 124.2, "CNPJ / CPF / NIF", d._cnpj_cpf(prest))
    p.campo(2, 124.2, "Inscrição Municipal", t(inf, "emit/IM") or t(prest, "IM"))
    p.campo(3, 124.2, "Telefone", d._fmt_telefone(t(inf, "emit/fone") or t(prest, "fone")))
    p.campo(0, 146.6, "Nome / Nome Empresarial", t(inf, "emit/xNome"), 2)
    p.campo(2, 146.6, "E-mail", t(inf, "emit/email") or t(prest, "email"), 2)
    ender = [t(inf, f"emit/enderNac/{k}") for k in ("xLgr", "nro", "xCpl", "xBairro")]
    p.campo(0, 167.8, "Endereço", ", ".join(x for x in ender if x) or "-", 2)
    p.campo(2, 167.8, "Município", _municipio_uf(municipio, uf))
    p.campo(3, 167.8, "CEP", _cep(t(inf, "emit/enderNac/CEP")))
    op = t(prest, "regTrib/opSimpNac")
    p.campo(0, 189.0, "Simples Nacional na Data de Competência", d._traduzir(_OP_SIMP, op, "Simples Nacional"), 2)
    reg_ap = t(prest, "regTrib/regApTribSN")
    p.campo(2, 189.0, "Regime de Apuração Tributária pelo SN",
            d._traduzir(d._REG_AP_TRIB_SN, reg_ap, "Regime de Apuração Tributária pelo SN") if reg_ap else "-", 2)
    p.filete(209.6)

    # ---- tomador
    if toma is None:
        p.texto(0, 210.7, "TOMADOR DO SERVIÇO NÃO IDENTIFICADO NA NFS-e", 8, centro=(ESQ + DIR) / 2)
        base = 209.6 + 9.6
        p.filete(base)
        y_serv = base
    else:
        p.titulo(210.9, "TOMADOR DO SERVIÇO")
        p.campo(1, 210.7, "CNPJ / CPF / NIF", d._cnpj_cpf(toma))
        p.campo(2, 210.7, "Inscrição Municipal", t(toma, "IM"))
        p.campo(3, 210.7, "Telefone", d._fmt_telefone(t(toma, "fone")))
        p.campo(0, 232.0, "Nome / Nome Empresarial", t(toma, "xNome"), 2)
        p.campo(2, 232.0, "E-mail", t(toma, "email"), 2)
        end = [t(toma, f"end/{k}") for k in ("xLgr", "nro", "xCpl", "xBairro")]
        linhas_end = _linhas(", ".join(x for x in end if x) or "-", COL * 2 - 8, 2)
        p.rotulo(0, 253.2, "Endereço")
        for k, ln in enumerate(linhas_end):
            p.texto(X[0], 261.3 + 9.0 * k, ln, 8)
        p.campo(2, 253.2, "Município", _tomador_cidade(toma))
        p.campo(3, 253.2, "CEP", _cep(t(toma, "end/endNac/CEP")))
        fim_toma = 273.8 + (9.0 if len(linhas_end) > 1 else 0.0) + 0.0
        fim_toma = 282.8 if len(linhas_end) > 1 else 273.8
        p.filete(fim_toma)
        base = fim_toma
        p.texto(0, base + 1.3, "INTERMEDIÁRIO DO SERVIÇO NÃO IDENTIFICADO NA NFS-e", 8, centro=(ESQ + DIR) / 2)
        y_serv = base + 9.6
        p.filete(y_serv)

    # ---- serviço prestado
    b = y_serv
    p.titulo(b + 1.3, "SERVIÇO PRESTADO")
    cod_nac = d._fmt_trib_nac(t(serv, "cTribNac"))
    cod_mun = t(serv, "cTribMun")
    p.rotulo(0, b + 16.9, "Código de Tributação Nacional")
    for k, ln in enumerate(_linhas(_limitar66(f"{cod_nac} - {t(inf, 'xTribNac') or ''}".rstrip(" -")), COL - 5, 2)):
        p.texto(X[0], b + 25.0 + 9.0 * k, ln, 8)
    p.rotulo(1, b + 16.9, "Código de Tributação Municipal")
    if cod_mun:
        for k, ln in enumerate(_linhas(_limitar66(f"{cod_mun} - {t(inf, 'xTribMun') or ''}".rstrip(" -")), COL - 5, 2)):
            p.texto(X[1], b + 25.0 + 9.0 * k, ln, 8)
    else:
        p.valor(1, b + 25.0, "-")
    p.campo(2, b + 16.9, "Local da Prestação", _municipio_uf(t(inf, "xLocPrestacao"), uf))
    p.campo(3, b + 16.9, "País da Prestação", "-")
    p.rotulo(0, b + 47.2, "Descrição do Serviço")
    linhas_desc: list[str] = []
    for bruta in (t(serv, "xDescServ") or "-").splitlines() or ["-"]:
        limpa = " ".join(bruta.split())
        if limpa:
            linhas_desc += d._quebrar(limpa, DIR - X[0] - 6, _FONTE, 8)
    linhas_desc = linhas_desc or ["-"]
    for k, ln in enumerate(linhas_desc):
        p.texto(X[0], b + 55.2 + 9.05 * k, ln, 8)
    fim = b + 55.2 + 9.05 * max(len(linhas_desc), 3) + 3.6
    p.filete(fim)

    # ---- tributação municipal
    b = fim
    p.titulo(b + 1.4, "TRIBUTAÇÃO MUNICIPAL")
    trib_issqn = t(trib, "tribISSQN")
    p.campo(0, b + 14.5, "Tributação do ISSQN", d._traduzir(d._TRIB_ISSQN, trib_issqn, "Tributação do ISSQN"))
    p.campo(1, b + 14.5, "País Resultado da Prestação do Serviço", "-")
    p.campo(2, b + 14.5, "Município de Incidência do ISSQN", _municipio_uf(t(inf, "xLocIncid"), uf))
    reg_esp = t(prest, "regTrib/regEspTrib")
    p.campo(3, b + 14.5, "Regime Especial de Tributação", d._traduzir(_REG_ESP, reg_esp, "Regime Especial") if reg_esp else "-")
    imun = t(trib, "tpImunidade")
    p.campo(0, b + 35.8, "Tipo de Imunidade", d._traduzir(_TP_IMUN, imun, "Tipo de Imunidade") if imun else "-")
    p.campo(1, b + 35.8, "Suspensão da Exigibilidade do ISSQN", "Sim" if t(trib, "exigSusp/tpSusp") else "Não")
    p.campo(2, b + 35.8, "Número Processo Suspensão", t(trib, "exigSusp/nProcesso"))
    p.campo(3, b + 35.8, "Benefício Municipal", t(trib, "BM/nBM"))
    v_serv = d._moeda(t(dps, "valores/vServPrest/vServ"))
    p.campo(0, b + 57.0, "Valor do Serviço", v_serv)
    p.campo(1, b + 57.0, "Desconto Incondicionado", d._moeda(t(dps, "valores/vDescCondIncond/vDescIncond")))
    p.campo(2, b + 57.0, "Total Deduções/Reduções", d._moeda(t(dps, "valores/vDedRed/vDR")) if t(dps, "valores/vDedRed/vDR") else "-")
    p.campo(3, b + 57.0, "Cálculo do BM", d._moeda(t(trib, "BM/vRedBCBM")) if t(trib, "BM/vRedBCBM") else "-")
    p.campo(0, b + 78.2, "BC ISSQN", d._moeda(t(inf, "valores/vBC")) if t(inf, "valores/vBC") else "-")
    p.campo(1, b + 78.2, "Alíquota Aplicada", _fmt_aliq(t(inf, "valores/pAliqAplic")) if t(inf, "valores/pAliqAplic") else "-")
    p.campo(2, b + 78.2, "Retenção do ISSQN", d._traduzir(d._TP_RET_ISSQN, t(trib, "tpRetISSQN"), "Retenção do ISSQN"))
    p.campo(3, b + 78.2, "ISSQN Apurado", d._moeda(t(inf, "valores/vISSQN")) if t(inf, "valores/vISSQN") else "-")
    b += 98.8
    p.filete(b)

    # ---- tributação federal
    p.titulo(b + 1.3, "TRIBUTAÇÃO FEDERAL")
    p.campo(0, b + 14.4, "IRRF", "-")
    p.campo(1, b + 14.4, "Contribuição Previdenciária - Retida", "-")
    p.campo(2, b + 14.4, "Contribuições Sociais - Retidas", "-")
    p.campo(3, b + 14.4, "Descrição Contrib. Sociais - Retidas", "-")
    p.campo(0, b + 35.7, "PIS - Débito Apuração Própria", "-")
    p.campo(1, b + 35.7, "COFINS - Débito Apuração Própria", "-")
    b += 56.2
    p.filete(b)

    # ---- valor total
    p.titulo(b + 1.3, "VALOR TOTAL DA NFS-E")
    p.campo(0, b + 14.5, "Valor do Serviço", v_serv)
    p.campo(1, b + 14.5, "Desconto Condicionado", "-")
    p.campo(2, b + 14.5, "Desconto Incondicionado", "-")
    p.campo(3, b + 14.5, "ISSQN Retido", "-")
    p.campo(0, b + 35.7, "Total das Retenções Federais", "-")
    p.campo(1, b + 35.7, "PIS/COFINS - Débito Apur. Própria", "-")
    p.rotulo(3, b + 35.7, "Valor Líquido da NFS-e")
    p.texto(X[3], b + 43.8, d._moeda(t(inf, "valores/vLiq")), 8, True)
    b += 56.3
    p.filete(b)

    # ---- totais aproximados
    p.titulo(b + 1.3, "TOTAIS APROXIMADOS DOS TRIBUTOS")
    for k, nome in enumerate(("Federais", "Estaduais", "Municipais")):
        cx = ESQ + (DIR - ESQ) / 6 * (2 * k + 1)
        p.texto(0, b + 14.5, nome, 7, True, centro=cx)
        p.texto(0, b + 22.5, "-", 8, centro=cx)
    b += 35.0
    p.filete(b)

    # ---- informações complementares
    p.titulo(b + 1.3, "INFORMAÇÕES COMPLEMENTARES")
    compl = t(dps, "infoCompl/xInfComp")
    if compl:
        for k, ln in enumerate(d._quebrar(" ".join(compl.split()), DIR - X[0] - 6, _FONTE, 8)):
            p.texto(X[0], b + 14.5 + 9.05 * k, ln, 8)

    if marca_dagua:
        c.saveState()
        c.setFont(d._FONTE_TITULO_REGULAR, 60)
        c.setFillColor(colors.Color(0.35, 0.35, 0.35, alpha=0.35))
        c.translate(W / 2, H / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, marca_dagua)
        c.restoreState()
    c.showPage()
    c.save()
    return buf.getvalue()
