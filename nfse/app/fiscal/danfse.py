# -*- coding: utf-8 -*-
"""Geração própria do DANFSe v2.0, conforme Nota Técnica SE/CGNFS-e nº
008/2026 (v1.02, 14/07/2026) -- gov.br/nfse/.../nt-008-se-cgnfse-danfse-
20260714-v1-02.pdf.

A API de geração do DANFSe do governo (adn.nfse.gov.br/danfse/{chave})
foi desativada em 03/08/2026 -- a partir daí a geração é responsabilidade
de cada sistema emissor. Este módulo lê o XML OFICIAL da NFS-e (já salvo
em `nfse_emitida.xml_nfse` no momento da autorização pela Sefin Nacional
-- nenhuma segunda fonte/estrutura de dados) e monta o PDF a partir dele,
nunca dos dados internos do pedido/empresa -- exatamente o que o item 2.1
da NT exige ("Os campos do DANFSe deverão representar o conteúdo das
respectivas TAG XML da NFS-e emitida").

Revisão de 2026-09-11 (2ª rodada): a primeira revisão (mesmo dia) corrigiu
os dados (bug do "Retenção do ISSQN", fonte do Prestador). Esta segunda
revisão troca TODO o motor de desenho: em vez de tabelas Platypus com
grade cinza em toda célula (uma aproximação visual), o layout agora é
desenhado com coordenadas físicas absolutas (reportlab.pdfgen.canvas),
replicando o leiaute medido diretamente do DANFSe real emitido pela Sefin
Nacional para a NFS-e nº 31 (mesma chave, baixado do Portal Nacional) e
as regras de fonte/sombreamento da própria NT (itens 2.2.3 e 2.4):
- Fontes reais Arial (títulos) e Microsoft Sans Serif (conteúdo)
  incorporadas ao PDF a partir de `app/fiscal/fonts/*.ttf` -- cópias dos
  arquivos do Windows (arial.ttf, arialbd.ttf, micross.ttf). Isso troca a
  aproximação anterior (Helvetica) pela fonte pedida pela NT. Como são
  arquivos de fonte da Microsoft, a incorporação aqui segue o mesmo uso
  de "gerar um documento" que qualquer programa (Word, navegador) faz ao
  exportar PDF com essas fontes instaladas -- mas vale registrar que
  redistribuir os `.ttf` em si (não apenas o PDF gerado) é uma cópia da
  fonte da Microsoft, então isso deve ser confirmado como aceitável para
  o ambiente de produção (Render/Linux não tem essas fontes do sistema
  operacional -- por isso os arquivos precisam estar no repositório).
- Logomarca oficial da NFS-e (`app/fiscal/assets/nfse_logo.png`) baixada
  da própria URL que a NT indica no item 2.4.3
  (gov.br/nfse/.../logos-da-nfs-e/Logo%20-%20NFS-e%20-%20Horizontal.png)
  -- não é mais um selo textual "NFS-e" de aproximação, nem o logo da
  LicitPrint (removido na revisão anterior).
- Sombreamento cinza claro (~5% -- RGB 242/242/242, medido por pixel no
  PDF real) aplicado exatamente onde a NT manda: cabeçalho, títulos de
  cada bloco de campos, campo "Emitente da NFS-e" e campo "Valor Líquido
  da NFS-e + IBS/CBS" -- nenhum outro campo. Confirmado pixel a pixel
  contra o PDF real (nenhuma outra célula tem fundo cinza nele).
  Confirmado também que os títulos de bloco (PRESTADOR/FORNECEDOR,
  TOMADOR/ADQUIRENTE, SERVIÇO PRESTADO, TRIBUTAÇÃO MUNICIPAL (ISSQN),
  TRIBUTAÇÃO FEDERAL (EXCETO CBS), TRIBUTAÇÃO IBS/CBS, VALOR TOTAL DA
  NFS-e) ocupam só a largura da 1ª coluna da grade de 4 colunas e ficam
  na MESMA linha do primeiro grupo de campos daquele bloco -- não numa
  linha própria acima. "Destinatário"/"Intermediário não identificado" e
  "Informações Complementares" são texto simples em negrito, sem
  sombreamento, ocupando a largura inteira.
- Linhas divisórias finas (0,5pt) só entre blocos/linhas -- SEM grade
  vertical em volta de cada campo (o PDF real não tem essa grade; a
  versão anterior deste módulo tinha, o que era uma aproximação visual
  errada). Borda externa da página em 1pt.
- QR Code nas dimensões e posição da NT (1,52 x 1,52cm, canto superior
  direito do bloco de identificação).

Revisão de 2026-09-11 (3ª rodada): correção EXCLUSIVA de layout (nenhum
dado mudou) -- comparação vetorial campo a campo contra o PDF real (não só
visual: coordenadas de texto e de linhas/retângulos extraídas do próprio
PDF oficial via biblioteca de baixo nível), que revelou que a 2ª rodada
tinha 3 problemas reais de geometria:
- Linhas divisórias demais: o PDF real só traça linha entre BLOCOS
  (Prestador, Tomador, Serviço, cada Tributação, Valor Total) -- dentro de
  um bloco as várias linhas de campo (ex.: CNPJ / Nome / Endereço / Simples
  Nacional do Prestador) são separadas só por espaço em branco, sem regua
  nenhuma. A versão anterior traçava uma linha após cada linha de campo,
  o que "picava" o layout e dava a impressão de comprimido.
- Altura de linha pequena demais: 0,62cm uniforme, contra os 20,2pt
  (bloco de identificação) / 19,1pt (demais blocos) medidos no PDF real --
  aumentado para `ALTURA_ID`/`ALTURA` (medidos, não arredondados por
  estética).
- Bloco Tributação IBS/CBS com campo por coluna errado (tinha uma linha a
  mais e agrupava campos diferentes do oficial) e rodapé (canhoto) com a
  3ª coluna (Nº/Chave da NFS-e) estreita demais -- truncava a chave.
  Ambos corrigidos com o mapeamento exato de coluna/linha do PDF real.
Também: avisos de "não identificado" agora centralizados (eram alinhados
à esquerda) e QR Code no tamanho exato medido (1,587cm, não 1,52cm).

Revisão de 2026-09-11 (4ª rodada): revisão final de rótulos/formatação,
comparando span a span (texto extraído do PDF vetorial oficial, não visual)
-- sem mexer em nenhuma regra fiscal:
- Telefone formatado "(DD) NNNNN-NNNN"/"(DD) NNNN-NNNN" (`_fmt_telefone`)
  -- antes mostrava os dígitos crus.
- Rótulos em maiúsculas ("NÚMERO DA NFS-e" etc.) preservavam errado o "E"
  de "NFS-e" (ficava "NFS-E") -- corrigido com `_rotulo_maiusculo`, que
  maiusculiza mas preserva a grafia oficial "NFS-e". Mesma correção nos
  rótulos do canhoto (eram exibidos em texto normal; o PDF real usa
  maiúsculas) e nos 3 campos de valor "grandes" do bloco Valor Total
  (Valor da Operação/Serviço, Valor Líquido da NFS-e, Valor Líquido +
  IBS/CBS -- só esses 3 ficam em maiúsculas no PDF real, os demais campos
  do bloco continuam em texto normal, conferido campo a campo).
- Rótulo "Competência" estava faltando o sufixo "da NFS-e" do PDF real.
  "Email" -> "E-mail" (grafia do PDF real, com hífen).
- QR Code: URL gerada dinamicamente a partir da chave desta NFS-e
  específica (nunca fixa) -- ajustada de
  ".../ConsultaPublica/?tpc=1&chave=..." (barra a mais antes do "?") para
  ".../ConsultaPublica?tpc=1&chave=..." depois de decodificar o QR de um
  DANFSe real e comparar a URL byte a byte.
- Canhoto: campo "Data Cientificação" não deve vir pré-preenchido com
  "____/____/________" -- no PDF real esse espaço fica em branco (é
  preenchido à mão depois de impresso).
- Exibição de NFS-e cancelada: confirmado que o único indicador visual
  (a marca d'água diagonal "CANCELADA") continua correta -- o restante do
  documento (inclusive "Situação da NFS-e") não muda, porque o XML oficial
  não é reemitido pelo governo quando cancelamos depois (regra do
  usuário: nunca inventar/alterar dado que não veio do XML).

Nível de fidelidade / limites conhecidos: o motor calcula a posição
vertical de cada bloco dinamicamente (um "cursor" que desce a cada bloco
desenhado), replicando o efeito das supressões previstas nos itens 2.3 e
notas 2-5 da NT (bloco vira uma linha só quando o dado não existe) -- mas
os tamanhos de coluna usam uma grade uniforme de 4 colunas (5,10cm cada)
em vez dos milímetros exatos linha a linha do item 2.4.5 (a própria NT
diz que esses tamanhos são sugestão, não obrigatoriedade -- item 2.1).
O bloco de Tributação IBS/CBS sai com "-" em quase todos os campos
(regime de transição da reforma tributária -- nossas DPS não carregam
esse grupo). Município do tomador: quando o tomador tem endereço
nacional, o XML só traz o código IBGE (`cMun`), não o nome da cidade --
sem tabela de municípios embutida, o campo mostra o código (nunca inventa
um nome), podendo divergir visualmente do DANFSe oficial nesse campo
específico.
"""

import io
import os
from datetime import datetime

import qrcode
from lxml import etree

from . import xmlseguro
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as _canvas_mod

_NS = {"n": "http://www.sped.fazenda.gov.br/nfse"}

# Versão do motor de desenho -- `nfse.obter_danfse_pdf` compara com
# `nfse_emitida.danfse_versao` pra saber se o PDF cacheado é de uma versão
# anterior do layout e precisa ser remontado (migração 010). Incrementar
# SEMPRE que este arquivo mudar algo visível no PDF (layout, rótulo,
# formatação) -- esquecer disso faz NFS-e já emitidas continuarem
# mostrando o layout velho pra sempre, mesmo depois do deploy da correção.
VERSAO_LAYOUT = 8

# ---------------------------------------------------------------------------
# Fontes oficiais (item 2.4 da NT: Arial p/ títulos, Microsoft Sans Serif p/
# conteúdo) -- incorporadas a partir de cópias dos arquivos reais do Windows.
# ---------------------------------------------------------------------------
_DIR = os.path.dirname(__file__)
_FONTE_TITULO = "Arial-Bold"
_FONTE_TITULO_REGULAR = "Arial"
_FONTE_CONTEUDO = "MSSansSerif"
if _FONTE_TITULO not in pdfmetrics.getRegisteredFontNames():
    pdfmetrics.registerFont(TTFont(_FONTE_TITULO_REGULAR, os.path.join(_DIR, "fonts", "arial.ttf")))
    pdfmetrics.registerFont(TTFont(_FONTE_TITULO, os.path.join(_DIR, "fonts", "arialbd.ttf")))
    pdfmetrics.registerFont(TTFont(_FONTE_CONTEUDO, os.path.join(_DIR, "fonts", "micross.ttf")))

_LOGO_PATH = os.path.join(_DIR, "assets", "nfse_logo.png")

# ---------------------------------------------------------------------------
# Geometria: coordenadas físicas absolutas em pontos PDF, convertidas de cm.
# yTop é medido a partir do TOPO da página (mais fácil de raciocinar bloco a
# bloco); `_y()` converte para o sistema de coordenadas do reportlab (origem
# no canto inferior esquerdo).
# ---------------------------------------------------------------------------
PT_PER_CM = 28.3464567
PAGE_W, PAGE_H = A4  # 595.27 x 841.89 pt (A4 retrato, item 2.2.1)

_BORDA_CM = 0.15  # item 2.2.2: margem entre o corpo impresso e a borda
X1, X2, X3, X4 = 0.30, 5.40, 10.50, 15.60
LARG_COL = 5.10
DIREITA = 20.70
LARG_TOTAL = DIREITA - X1

# Alturas de linha medidas diretamente no DANFSe real (NFS-e nº 31, PDFsharp/
# Sefin Nacional) via coordenadas vetoriais do PDF (não da imagem renderizada)
# -- ver comparação pixel-a-pixel de 2026-09-11 (3ª rodada). O bloco de
# identificação (chave/número/dps/emitente) usa rótulo de 7pt e linha de
# 20,2pt; os demais blocos usam rótulo de 6pt e linha de 19,1pt. Usar essas
# alturas (em vez de um valor único comprimido) é o que faz o layout "abrir"
# como o documento oficial -- NÃO reduzir para economizar espaço.
ALTURA_ID = 20.2 / PT_PER_CM
ALTURA = 19.1 / PT_PER_CM
ALTURA_TEXTO_LIVRE = 12.3 / PT_PER_CM
ALTURA_AVISO = 8.4 / PT_PER_CM
GAP_APOS_TITULO_INFO = 20.0 / PT_PER_CM

_CINZA_5PC = colors.Color(242 / 255, 242 / 255, 242 / 255)  # item 2.2.3: 5% de cinza
_PRETO = colors.black


def _cm(v: float) -> float:
    return v * PT_PER_CM


def _y(top_cm: float) -> float:
    return PAGE_H - _cm(top_cm)


# ---------------------------------------------------------------------------
# Extração e formatação de dados -- lê exclusivamente o XML oficial da NFS-e.
# Regra do usuário: NUNCA inventar, inferir ou recalcular dado tributário.
# ---------------------------------------------------------------------------

_TP_EMIT = {"1": "Prestador", "2": "Tomador", "3": "Intermediário"}
_OP_SIMP_NAC = {
    "1": "Não Optante",
    "2": "Optante - Microempreendedor Individual (MEI)",
    "3": "Optante - Microempresa ou Empresa de Pequeno Porte (ME/EPP)",
}
_REG_AP_TRIB_SN = {
    "1": "Regime de apuração dos tributos federais e municipal pelo Simples Nacional",
}
_TRIB_ISSQN = {"1": "Operação Tributável", "2": "Operação Não Tributável", "3": "Imune", "4": "Exportação"}
# Confirmado contra o DANFSe oficial das NFS-e 30 e 31 (tpRetISSQN=1 nas duas,
# mostrando "Não Retido" no PDF do Portal Nacional). Domínio errado antes de
# 2026-09-11: {"1": "Retido pelo Tomador/Intermediário", ...}.
_TP_RET_ISSQN = {"1": "Não Retido", "2": "Retido pelo Tomador", "3": "Retido pelo Intermediário"}
# Confirmado contra um DANFSe real baixado do portal pra essa mesma NFS-e (nº 31):
# cStat=100 mostra "NFS-e Gerada", não "NFS-e Autorizada" como se poderia supor.
_C_STAT = {"100": "NFS-e Gerada"}


class DanfseIndisponivel(Exception):
    """XML da NFS-e ausente/não reconhecido, ou um código tributário sem
    mapeamento conhecido -- em qualquer um dos casos não dá pra montar o
    DANFSe com segurança (regra do usuário: nunca inventar/adivinhar dado
    tributário)."""


def _t(no, caminho: str) -> str | None:
    """Texto de um elemento filho (caminho relativo, ex.: "emit/CNPJ") ou None."""
    if no is None:
        return None
    achado = no.find("n:" + "/n:".join(caminho.split("/")), namespaces=_NS)
    return achado.text.strip() if achado is not None and achado.text else None


def _traduzir(mapa: dict, codigo: str | None, rotulo: str) -> str:
    """Traduz um código da NFS-e pro texto oficial do domínio. Nunca
    "aproxima" a tradução de um código que não conhece -- levanta erro em
    vez de arriscar mostrar o texto errado de outro código (foi assim que
    o bug da Retenção do ISSQN aconteceu)."""
    if not codigo:
        return "-"
    if codigo not in mapa:
        raise DanfseIndisponivel(
            f"Divergência de dados no DANFSe -- CAMPO: {rotulo} | VALOR NO XML: {codigo!r} | "
            f"DIVERGÊNCIA: não existe mapeamento conhecido pra esse código. Não é seguro gerar "
            f"o PDF adivinhando o texto -- é preciso atualizar o mapeamento no sistema."
        )
    return mapa[codigo]


def _cnpj_cpf(no) -> str:
    for tag in ("CNPJ", "CPF", "NIF"):
        v = _t(no, tag)
        if v:
            if tag == "CNPJ" and len(v) == 14:
                return f"{v[:2]}.{v[2:5]}.{v[5:8]}/{v[8:12]}-{v[12:]}"
            if tag == "CPF" and len(v) == 11:
                return f"{v[:3]}.{v[3:6]}.{v[6:9]}-{v[9:]}"
            return v
    return "-"


def _endereco(no) -> str:
    partes = [_t(no, f"end/{c}") for c in ("xLgr", "nro", "xCpl", "xBairro")]
    partes = [p for p in partes if p]
    return ", ".join(partes) if partes else "-"


def _endereco_emit(inf_nfse) -> str:
    """Endereço do prestador -- vem de `infNFSe/emit/enderNac`, estrutura
    diferente do endereço do tomador (`toma/end/...`): aqui os campos
    ficam direto dentro de `enderNac`, sem o wrapper `end`."""
    partes = [_t(inf_nfse, f"emit/enderNac/{c}") for c in ("xLgr", "nro", "xCpl", "xBairro")]
    partes = [p for p in partes if p]
    return ", ".join(partes) if partes else "-"


_MUNICIPIOS: dict[str, str] | None = None


def nome_municipio_ibge(codigo: str | None) -> tuple[str, str] | None:
    """(nome, UF) pelo código IBGE -- tabela oficial embutida (municipios_ibge.json, gerada da
    API de localidades do IBGE), igual ao que o DANFSe do Portal Nacional mostra."""
    global _MUNICIPIOS
    if not codigo:
        return None
    if _MUNICIPIOS is None:
        import json
        caminho = os.path.join(os.path.dirname(__file__), "municipios_ibge.json")
        with open(caminho, encoding="utf-8") as f:
            _MUNICIPIOS = json.load(f)
    valor = _MUNICIPIOS.get(codigo)
    if not valor:
        return None
    nome, uf = valor.split("|")
    return nome, uf


def _municipio_uf(no) -> str:
    cmun = _t(no, "end/endNac/cMun")
    uf = _t(no, "end/endNac/UF")
    if cmun:
        # O XML só traz o código IBGE do tomador -- o nome vem da tabela do IBGE; código
        # fora da tabela continua aparecendo como código (nunca um nome inventado).
        achado = nome_municipio_ibge(cmun)
        if achado:
            return f"{achado[0]} / {achado[1]}"
        return f"{cmun} / {uf or '-'}"
    xcidade = _t(no, "end/endExt/xCidade")
    return f"{xcidade} / {uf or '-'}" if xcidade else "-"


def _fmt_ibge(codigo: str | None) -> str:
    if not codigo or len(codigo) < 3:
        return codigo or "-"
    return f"{codigo[:2]}.{codigo[2:]}"


def _fmt_cep(codigo: str | None) -> str:
    if not codigo or len(codigo) != 8:
        return codigo or "-"
    return f"{codigo[:2]}.{codigo[2:5]}-{codigo[5:]}"


def _fmt_nbs(codigo: str | None) -> str:
    if not codigo or len(codigo) != 9:
        return codigo or "-"
    return f"{codigo[0]}.{codigo[1:5]}.{codigo[5:7]}.{codigo[7:]}"


def _fmt_trib_nac(codigo: str | None) -> str:
    if not codigo or len(codigo) != 6:
        return codigo or "-"
    return f"{codigo[:2]}.{codigo[2:4]}.{codigo[4:]}"


def _fmt_telefone(v: str | None) -> str:
    """(DD) NNNNN-NNNN (celular, 11 dígitos) ou (DD) NNNN-NNNN (fixo, 10) --
    confirmado contra o DANFSe real ("(31) 99914-3468"). Fora desse
    formato (ex.: telefone internacional), mostra o valor cru em vez de
    arriscar uma formatação errada."""
    if not v:
        return "-"
    digitos = "".join(ch for ch in v if ch.isdigit())
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"
    return v


def _ibge_cep_toma(no) -> str:
    cmun = _t(no, "end/endNac/cMun")
    cep = _t(no, "end/endNac/CEP")
    return f"{_fmt_ibge(cmun)} / {_fmt_cep(cep)}" if (cmun or cep) else "-"


def _ibge_cep_emit(inf_nfse) -> str:
    cmun = _t(inf_nfse, "emit/enderNac/cMun")
    cep = _t(inf_nfse, "emit/enderNac/CEP")
    return f"{_fmt_ibge(cmun)} / {_fmt_cep(cep)}" if (cmun or cep) else "-"


def _moeda(valor: str | None) -> str:
    if not valor:
        return "-"
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    except ValueError:
        return valor


def _data_br(iso: str | None) -> str:
    if not iso:
        return "-"
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return iso


def _data_hora_br(iso: str | None) -> str:
    if not iso:
        return "-"
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return iso


# ---------------------------------------------------------------------------
# Primitivas de desenho -- texto sempre ajustado à largura da célula (item 19
# da especificação do usuário: nunca deixar o texto vazar a coluna/borda).
# ---------------------------------------------------------------------------

def _ajustar(texto: str, largura_pt: float, fonte: str, tamanho: float) -> str:
    """Trunca com reticências se o texto não couber na largura -- nunca deixa
    vazar a célula (regra do item 2.4.5 da NT: preencher com reticências)."""
    texto = texto or "-"
    if pdfmetrics.stringWidth(texto, fonte, tamanho) <= largura_pt:
        return texto
    while texto and pdfmetrics.stringWidth(texto + "...", fonte, tamanho) > largura_pt:
        texto = texto[:-1]
    return (texto + "...") if texto else "..."


def _limitar(texto: str | None, limite: int) -> str:
    """Corte por nº de caracteres da NT 008 (tabela do item 2.4.5): "Preencher com reticências
    (...), caso a descrição supere N caracteres" -- é assim que o DANFSe do Portal Nacional
    corta (ex.: Simples Nacional em 37, descrição da tributação nacional em 167), não pela
    largura da célula."""
    texto = " ".join((texto or "").split())
    if not texto:
        return "-"
    return texto[:limite] + "..." if len(texto) > limite else texto


def _quebrar(texto: str, largura_pt: float, fonte: str, tamanho: float, max_linhas: int | None = None) -> list[str]:
    """Quebra o texto em linhas que cabem na largura, em quantas linhas precisar (como o
    DANFSe do portal faz na Descrição do Serviço). Com `max_linhas`, para nessa quantidade
    e põe reticências na última. Espaços repetidos viram um só (o portal faz o mesmo)."""
    palavras = (texto or "-").split() or ["-"]
    linhas: list[str] = []
    atual = ""
    for palavra in palavras:
        candidato = f"{atual} {palavra}" if atual else palavra
        if pdfmetrics.stringWidth(candidato, fonte, tamanho) <= largura_pt:
            atual = candidato
            continue
        if atual:
            linhas.append(atual)
        # Palavra sozinha mais larga que a linha (ex.: URL): quebra por caractere.
        while pdfmetrics.stringWidth(palavra, fonte, tamanho) > largura_pt and len(palavra) > 1:
            corte = len(palavra)
            while corte > 1 and pdfmetrics.stringWidth(palavra[:corte], fonte, tamanho) > largura_pt:
                corte -= 1
            linhas.append(palavra[:corte])
            palavra = palavra[corte:]
        atual = palavra
    if atual:
        linhas.append(atual)
    if max_linhas and len(linhas) > max_linhas:
        resto = " ".join(linhas[max_linhas - 1:])
        linhas = linhas[:max_linhas - 1] + [_ajustar(resto, largura_pt, fonte, tamanho)]
    return linhas


def _rotulo_maiusculo(texto: str) -> str:
    """Maiusculiza um rótulo preservando a grafia oficial "NFS-e" -- o PDF
    real usa o rótulo todo em maiúsculas (ex.: "NÚMERO DA NFS-e") mas
    mantém o "e" minúsculo nessa marca, mesmo dentro do texto maiúsculo."""
    return texto.upper().replace("NFS-E", "NFS-e")


class _Renderizador:
    """Desenha o DANFSe com coordenadas absolutas, avançando um cursor
    vertical (`self.y`) bloco a bloco -- os blocos condicionalmente
    suprimidos (itens 2.3/notas 2-4 da NT) só ocupam uma linha fina, e tudo
    abaixo se reposiciona (igual ao comportamento do gerador oficial)."""

    def __init__(self, c: _canvas_mod.Canvas):
        self.c = c
        self.y = 0.30  # cursor vertical (cm a partir do topo)

    # -- utilidades de baixo nível --------------------------------------
    def _texto(self, x_cm, y_top_cm, texto, fonte, tamanho, cor=_PRETO, largura_cm=None):
        largura_pt = _cm(largura_cm) - 6 if largura_cm else 10_000
        texto = _ajustar(texto, largura_pt, fonte, tamanho)
        self.c.setFont(fonte, tamanho)
        self.c.setFillColor(cor)
        self.c.drawString(_cm(x_cm) + 3, _y(y_top_cm) - tamanho, texto)

    def _sombra(self, x_cm, y_top_cm, largura_cm, altura_cm):
        self.c.setFillColor(_CINZA_5PC)
        self.c.rect(_cm(x_cm), _y(y_top_cm + altura_cm), _cm(largura_cm), _cm(altura_cm), stroke=0, fill=1)

    def _linha(self, y_top_cm, x0_cm=X1 - 0.15, x1_cm=DIREITA + 0.15, espessura=0.5):
        self.c.setLineWidth(espessura)
        self.c.setStrokeColor(_PRETO)
        self.c.line(_cm(x0_cm), _y(y_top_cm), _cm(x1_cm), _y(y_top_cm))

    def _campo(self, x_cm, largura_cm, altura_cm, label, valor, sombreado=False, label_maiusculo=False,
               tam_label=6.0, tam_valor=7.0):
        if sombreado:
            self._sombra(x_cm, self.y, largura_cm, altura_cm)
        rotulo = _rotulo_maiusculo(label) if label_maiusculo else label
        self._texto(x_cm, self.y + 0.02, rotulo, _FONTE_TITULO, tam_label, largura_cm=largura_cm)
        # Rótulo->valor: ~0,8pt além da altura do rótulo (medido no PDF real:
        # 6,7pt de vão pra rótulo de 6pt, 7,8pt pra rótulo de 7pt).
        self._texto(x_cm, self.y + (tam_label + 0.8) / PT_PER_CM, valor or "-", _FONTE_CONTEUDO, tam_valor,
                    largura_cm=largura_cm)

    def _titulo_bloco(self, texto, altura_cm, largura_cm=LARG_COL, x_cm=X1, tam=7.0):
        self._sombra(x_cm, self.y, largura_cm, altura_cm)
        self.c.setFont(_FONTE_TITULO, tam)
        self.c.setFillColor(_PRETO)
        meio = self.y + altura_cm / 2
        self.c.drawString(_cm(x_cm) + 3, _y(meio) - tam / 2.8, _rotulo_maiusculo(texto))

    def _aviso(self, texto, altura_cm=ALTURA_AVISO):
        """Bloco suprimido (Nota 2/3/4): uma linha fina, negrito, centralizada,
        sem sombreamento, largura inteira -- exatamente como o DANFSe real
        mostra "DESTINATÁRIO.../INTERMEDIÁRIO..." (medido: 8,4pt de altura,
        texto centralizado na página, não alinhado à esquerda)."""
        centro_x = _cm(X1) + _cm(LARG_TOTAL) / 2
        tam = 7.0
        self.c.setFont(_FONTE_TITULO, tam)
        self.c.setFillColor(_PRETO)
        meio = self.y + altura_cm / 2
        self.c.drawCentredString(centro_x, _y(meio) - tam / 2.8, texto)
        self.y += altura_cm

    def linha_divisoria(self):
        self._linha(self.y)


def _qrcode_imagem(chave: str) -> ImageReader:
    """Gerado dinamicamente pela chave de acesso desta NFS-e específica --
    mesma URL (sem barra antes do "?") que o QR do DANFSe real do Portal
    Nacional codifica, confirmado decodificando o QR de um PDF oficial."""
    url = f"https://www.nfse.gov.br/ConsultaPublica?tpc=1&chave={chave}"
    img = qrcode.make(url, box_size=8, border=1)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return ImageReader(buffer)


def gerar_danfse_pdf_v2(xml_nfse: str, marca_dagua: str | None = None) -> bytes:
    """Monta o PDF do DANFSe v2.0 a partir do XML oficial da NFS-e (já
    autorizado pela Sefin Nacional), com coordenadas físicas absolutas
    replicando o leiaute do DANFSe real do Portal Nacional. Levanta
    DanfseIndisponivel se o XML estiver ausente/ilegível ou se algum código
    tributário não tiver mapeamento conhecido -- nunca inventa/adivinha dado
    que não está lá.

    `marca_dagua`: "CANCELADA" ou "SUBSTITUÍDA" (itens 2.5.1/2.5.2 da NT) --
    vem do nosso próprio status em `nfse_emitida`, não do XML (o governo
    não reemite XML quando cancelamos depois). Marca d'água diagonal
    cinza translúcida no meio da página (uma rodada anterior, no mesmo
    dia, tinha trocado isso por um rótulo vermelho no cabeçalho -- o
    usuário pediu pra voltar exatamente ao formato de marca d'água)."""
    if not xml_nfse:
        raise DanfseIndisponivel("Essa NFS-e não tem o XML oficial salvo -- não dá para montar o DANFSe.")
    try:
        raiz = xmlseguro.parse(xml_nfse)
    except (etree.XMLSyntaxError, ValueError) as e:
        raise DanfseIndisponivel(f"XML da NFS-e inválido: {e}") from e

    inf_nfse = raiz if raiz.tag.endswith("infNFSe") else raiz.find("n:infNFSe", namespaces=_NS)
    if inf_nfse is None:
        raise DanfseIndisponivel("XML não tem o elemento infNFSe esperado.")
    inf_dps = inf_nfse.find("n:DPS/n:infDPS", namespaces=_NS)
    if inf_dps is None:
        raise DanfseIndisponivel("XML não tem o elemento DPS/infDPS esperado.")

    chave = inf_nfse.get("Id", "").removeprefix("NFS")
    tp_amb = _t(inf_dps, "tpAmb")
    homologacao = tp_amb == "2"

    saida = io.BytesIO()
    c = _canvas_mod.Canvas(saida, pagesize=A4)
    r = _Renderizador(c)

    # ---- Borda externa da página (item 2.2.3: 1pt) ------------------------
    c.setLineWidth(1)
    c.setStrokeColor(_PRETO)
    c.rect(_cm(_BORDA_CM), _cm(_BORDA_CM), PAGE_W - 2 * _cm(_BORDA_CM), PAGE_H - 2 * _cm(_BORDA_CM), fill=0)

    # ---- Cabeçalho (item 2.4.3) --------------------------------------------
    altura_cab = 1.20
    r._sombra(X1, r.y, LARG_TOTAL, altura_cab)
    try:
        logo_img = ImageReader(_LOGO_PATH)
        lw, lh = logo_img.getSize()
        alt_logo_cm = 0.85
        larg_logo_cm = alt_logo_cm * lw / lh
        c.drawImage(logo_img, _cm(X1 + 0.15), _y(r.y + 0.16 + alt_logo_cm), _cm(larg_logo_cm), _cm(alt_logo_cm),
                    mask="auto")
    except Exception:
        pass

    c.setFont(_FONTE_TITULO, 9)
    c.setFillColor(_PRETO)
    centro_x = _cm(X1) + _cm(LARG_TOTAL) / 2
    c.drawCentredString(centro_x, _y(r.y + 0.42), "DANFSe v2.0")
    c.drawCentredString(centro_x, _y(r.y + 0.68), "Documento Auxiliar da NFS-e")
    if homologacao:
        c.setFillColor(colors.red)
        c.drawCentredString(centro_x, _y(r.y + 0.94), "NFS-e SEM VALIDADE JURÍDICA")

    municipio_emi = _t(inf_nfse, "xLocEmi") or "-"
    uf_emi = _t(inf_nfse, "emit/enderNac/UF") or ""
    r._texto(DIREITA - 6.2, r.y + 0.18, f"Município: {municipio_emi} - {uf_emi}", _FONTE_CONTEUDO, 8, largura_cm=6.2)
    r._texto(DIREITA - 6.2, r.y + 0.44, f"Ambiente Gerador: {_t(inf_nfse, 'ambGer') or '-'}", _FONTE_CONTEUDO, 6,
             largura_cm=6.2)
    r._texto(DIREITA - 6.2, r.y + 0.64, f"Tipo de Ambiente: {tp_amb or '-'}", _FONTE_CONTEUDO, 6, largura_cm=6.2)
    r.y += altura_cab
    r.linha_divisoria()

    # ---- Identificação da NFS-e + QR de autenticidade (itens 2.1.1/2.1.2) --
    situacao = _limitar(_traduzir(_C_STAT, _t(inf_nfse, "cStat"), "Situação da NFS-e"), 37)
    largura_qr_col = DIREITA - X4  # última coluna reservada ao QR
    largura_id = X4 - X1  # 3 colunas de texto à esquerda do QR

    y_qr_bloco = r.y
    r._texto(X1, r.y, "CHAVE DE ACESSO DA NFS-e", _FONTE_TITULO, 7, largura_cm=largura_id)
    r._texto(X1, r.y + 0.30, chave, _FONTE_CONTEUDO, 7.5, largura_cm=largura_id)
    r.y += ALTURA_ID

    linhas_id = [
        [("Número da NFS-e", _t(inf_nfse, "nNFSe") or "-"),
         ("Competência da NFS-e", _data_br(_t(inf_dps, "dCompet"))),
         ("Data e Hora da Emissão da NFS-e", _data_hora_br(_t(inf_nfse, "dhProc")))],
        [("Número da DPS", _t(inf_dps, "nDPS") or "-"),
         ("Série da DPS", _t(inf_dps, "serie") or "-"),
         ("Data e Hora da Emissão da DPS", _data_hora_br(_t(inf_dps, "dhEmi")))],
        [("Emitente da NFS-e", _traduzir(_TP_EMIT, _t(inf_dps, "tpEmit"), "Emitente da NFS-e")),
         ("Situação da NFS-e", situacao),
         ("Finalidade", "-")],
    ]
    # Bloco de identificação: SEM divisórias internas no DANFSe real -- só as
    # 4 linhas (chave/número/dps/emitente) separadas por espaço em branco,
    # com uma única linha ao final (antes do bloco Prestador).
    for i, linha in enumerate(linhas_id):
        for j, (label, valor) in enumerate(linha):
            x = [X1, X2, X3][j]
            sombrear = (i == 2 and j == 0)  # "Emitente da NFS-e" -- item 2.2.3
            r._campo(x, LARG_COL, ALTURA_ID, label, valor, sombreado=sombrear, label_maiusculo=True, tam_label=7)
        r.y += ALTURA_ID
    r.linha_divisoria()

    # QR Code + legenda, ocupando toda a altura do bloco de identificação
    # (item 2.4.3 -- 1,587cm, mesmo tamanho medido no PDF real da Sefin
    # Nacional; disposta em 3 linhas abaixo).
    lado_qr = 45 / PT_PER_CM
    qr_x = X4 + (largura_qr_col - lado_qr) / 2
    qr_y = y_qr_bloco
    c.drawImage(_qrcode_imagem(chave), _cm(qr_x), _y(qr_y + lado_qr), _cm(lado_qr), _cm(lado_qr), mask="auto")
    legenda = ("A autenticidade desta NFS-e pode ser verificada pela leitura deste código QR "
               "ou pela consulta da chave de acesso no portal nacional da NFS-e")
    for k, linha_legenda in enumerate(_quebrar(legenda, _cm(largura_qr_col) - 8, _FONTE_CONTEUDO, 6, 3)):
        r._texto(X4, qr_y + lado_qr + 0.10 + k * 0.24, linha_legenda, _FONTE_CONTEUDO, 6, largura_cm=largura_qr_col)
    c.setLineWidth(0.5)
    c.setStrokeColor(_PRETO)
    c.line(_cm(X4), _y(y_qr_bloco), _cm(X4), _y(r.y))

    # ---- Prestador / Fornecedor (item 2.1.3) -- nome e endereço vêm de
    # infNFSe/emit (dado oficial devolvido pela Sefin Nacional), nunca do
    # cadastro interno (`app.marca`).
    prest = inf_dps.find("n:prest", namespaces=_NS)
    fone_prest = _fmt_telefone(_t(prest, "fone"))
    email_prest = _t(prest, "email") or "-"
    op_simp = _t(prest, "regTrib/opSimpNac")
    reg_ap = _t(prest, "regTrib/regApTribSN")
    nome_prest = _limitar(_t(inf_nfse, "emit/xNome"), 77)
    endereco_prest = _limitar(_endereco_emit(inf_nfse), 77)

    # Bloco Prestador: 4 linhas de campos, SEM divisórias internas -- só uma
    # linha ao final (antes do bloco Tomador), igual ao DANFSe real.
    r._titulo_bloco("PRESTADOR / FORNECEDOR", ALTURA)
    r._campo(X2, LARG_COL, ALTURA, "CNPJ / CPF / NIF", _cnpj_cpf(prest))
    r._campo(X3, LARG_COL, ALTURA, "Indicador Municipal (Inscrição)", _t(prest, "IM") or "-")
    r._campo(X4, DIREITA - X4, ALTURA, "Telefone", fone_prest)
    r.y += ALTURA
    r._campo(X1, X3 - X1, ALTURA, "Nome / Nome Empresarial", nome_prest)
    r._campo(X3, LARG_COL, ALTURA, "Município / Sigla UF", f"{municipio_emi} / {uf_emi}")
    r._campo(X4, DIREITA - X4, ALTURA, "Código IBGE / CEP", _ibge_cep_emit(inf_nfse))
    r.y += ALTURA
    r._campo(X1, X3 - X1, ALTURA, "Endereço", endereco_prest)
    r._campo(X3, DIREITA - X3, ALTURA, "E-mail", email_prest)
    r.y += ALTURA
    r._campo(X1, LARG_COL, ALTURA, "Simples Nacional na Data de Competência",
             _limitar(_traduzir(_OP_SIMP_NAC, op_simp, "Simples Nacional na Data de Competência"), 37))
    r._campo(X2, DIREITA - X2, ALTURA, "Regime de Apuração Tributária pelo SN",
             _limitar(_traduzir(_REG_AP_TRIB_SN, reg_ap, "Regime de Apuração Tributária pelo SN"), 77))
    r.y += ALTURA
    r.linha_divisoria()

    # ---- Tomador / Adquirente (item 2.1.4) --------------------------------
    toma = inf_dps.find("n:toma", namespaces=_NS)
    if toma is None:
        r._aviso("TOMADOR/ADQUIRENTE DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e")
        r.linha_divisoria()
    else:
        r._titulo_bloco("TOMADOR / ADQUIRENTE", ALTURA)
        r._campo(X2, LARG_COL, ALTURA, "CNPJ / CPF / NIF", _cnpj_cpf(toma))
        r._campo(X3, LARG_COL, ALTURA, "Indicador Municipal (Inscrição)", _t(toma, "IM") or "-")
        r._campo(X4, DIREITA - X4, ALTURA, "Telefone", _fmt_telefone(_t(toma, "fone")))
        r.y += ALTURA
        r._campo(X1, X3 - X1, ALTURA, "Nome / Nome Empresarial", _limitar(_t(toma, "xNome"), 77))
        r._campo(X3, LARG_COL, ALTURA, "Município / Sigla UF", _municipio_uf(toma))
        r._campo(X4, DIREITA - X4, ALTURA, "Código IBGE / CEP", _ibge_cep_toma(toma))
        r.y += ALTURA
        r._campo(X1, X3 - X1, ALTURA, "Endereço", _limitar(_endereco(toma), 77))
        r._campo(X3, DIREITA - X3, ALTURA, "E-mail", _t(toma, "email") or "-")
        r.y += ALTURA
        r.linha_divisoria()

    # ---- Destinatário / Intermediário: suprimidos (item 2.3.1) -- não usados
    # no nosso modelo de DPS (só prestador -> tomador direto). No DANFSe real
    # cada aviso é uma linha fina isolada, com divisória própria (2 linhas +
    # 2 divisórias, sem espaço extra entre elas).
    r._aviso("DESTINATÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e")
    r.linha_divisoria()
    r._aviso("INTERMEDIÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e")
    r.linha_divisoria()

    # ---- Serviço Prestado (item 2.1.7) ------------------------------------
    serv = inf_dps.find("n:serv", namespaces=_NS)
    c_serv = serv.find("n:cServ", namespaces=_NS) if serv is not None else None

    r._titulo_bloco("SERVIÇO PRESTADO", ALTURA)
    r._campo(X2, LARG_COL, ALTURA, "Código de Tributação Nacional/Municipal",
             f"{_fmt_trib_nac(_t(c_serv, 'cTribNac'))} / {_t(c_serv, 'cTribMun') or '-'}")
    r._campo(X3, LARG_COL, ALTURA, "Código da NBS", _fmt_nbs(_t(c_serv, "cNBS")))
    r._campo(X4, DIREITA - X4, ALTURA, "Local da Prestação / Sigla UF / País",
             f"{_t(inf_nfse, 'xLocPrestacao') or '-'} / {uf_emi} / -")
    r.y += ALTURA
    # Sem título (label) -- observação explícita da NT (item 2.4.5).
    r._texto(X1, r.y + 0.05, _limitar(_t(c_serv, "xTribMun") or _t(inf_nfse, "xTribNac"), 167), _FONTE_CONTEUDO, 7,
             largura_cm=LARG_TOTAL)
    r.y += ALTURA_TEXTO_LIVRE
    # Texto inteiro, sempre, em quantas linhas precisar (a caixa cresce, item 2.3 da NT) -- nunca
    # corta. A emissão pelo sistema já barra descrição acima de 1297 caracteres (limite em que o
    # DANFSe do portal corta); nota registrada de fora com texto maior sai inteira mesmo assim.
    # Mantém as quebras de linha digitadas (ex.: "Itinerário:" em linha própria, como na nota modelo);
    # espaços repetidos dentro de cada linha valem um só.
    linhas_desc = []
    for bruta in (_t(c_serv, "xDescServ") or "-").splitlines() or ["-"]:
        limpa = " ".join(bruta.split())
        if limpa:
            linhas_desc += _quebrar(limpa, _cm(LARG_TOTAL) - 6, _FONTE_CONTEUDO, 7)
    linhas_desc = linhas_desc or ["-"]
    r._texto(X1, r.y + 0.02, "Descrição do Serviço", _FONTE_TITULO, 6, largura_cm=LARG_TOTAL)
    for k, linha_desc in enumerate(linhas_desc):
        r._texto(X1, r.y + 0.24 + k * 0.28, linha_desc, _FONTE_CONTEUDO, 7, largura_cm=LARG_TOTAL)
    r.y += max(ALTURA, 0.24 + len(linhas_desc) * 0.28 + 0.06)
    r.linha_divisoria()

    # ---- Tributação Municipal (ISSQN) (item 2.1.8) ------------------------
    trib_mun = inf_dps.find("n:valores/n:trib/n:tribMun", namespaces=_NS)
    if trib_mun is None:
        r._aviso("TRIBUTAÇÃO MUNICIPAL (ISSQN) - OPERAÇÃO NÃO SUJEITA AO ISSQN")
        r.linha_divisoria()
    else:
        r._titulo_bloco("TRIBUTAÇÃO MUNICIPAL (ISSQN)", ALTURA)
        r._campo(X2, LARG_COL, ALTURA, "Tipo de Tributação do ISSQN",
                 _traduzir(_TRIB_ISSQN, _t(trib_mun, "tribISSQN"), "Tipo de Tributação do ISSQN"))
        r._campo(X3, DIREITA - X3, ALTURA, "Município / Sigla UF / País de Incidência do ISSQN",
                 f"{_t(inf_nfse, 'xLocIncid') or '-'} / {uf_emi} / -")
        r.y += ALTURA
        r._campo(X1, LARG_COL, ALTURA, "BC ISSQN", "-")
        r._campo(X2, LARG_COL, ALTURA, "Alíquota Aplicada", "-")
        r._campo(X3, LARG_COL, ALTURA, "Retenção do ISSQN",
                 _traduzir(_TP_RET_ISSQN, _t(trib_mun, "tpRetISSQN"), "Retenção do ISSQN"))
        r._campo(X4, DIREITA - X4, ALTURA, "ISSQN Apurado", _moeda(_t(inf_dps, "valores/vISSQN")))
        r.y += ALTURA
        r.linha_divisoria()

    # ---- Tributação Federal (exceto CBS) (item 2.1.9) ---------------------
    r._titulo_bloco("TRIBUTAÇÃO FEDERAL (EXCETO CBS)", ALTURA)
    r._campo(X2, LARG_COL, ALTURA, "IRRF", "-")
    r._campo(X3, LARG_COL, ALTURA, "Contribuição Previdenciária - Retida", "-")
    r._campo(X4, DIREITA - X4, ALTURA, "Contribuições Sociais - Retidas", "-")
    r.y += ALTURA
    r._campo(X1, LARG_COL, ALTURA, "PIS - Débito Apuração Própria", "-")
    r._campo(X2, LARG_COL, ALTURA, "COFINS - Débito Apuração Própria", "-")
    r._campo(X3, DIREITA - X3, ALTURA, "Descrição Contrib. Sociais - Retidas", "-")
    r.y += ALTURA
    r.linha_divisoria()

    # ---- Tributação IBS/CBS (item 2.1.10) -- ainda não se aplica às nossas
    # notas (regime de transição da reforma tributária). Mapeamento de campo
    # por coluna conferido campo a campo contra o PDF real (4 linhas, não 5 --
    # divergia antes da revisão de 2026-09-11/3ª rodada).
    r._titulo_bloco("TRIBUTAÇÃO IBS/CBS", ALTURA)
    r._campo(X2, LARG_COL, ALTURA, "CST / cClassTrib", "- / -")
    r._campo(X3, DIREITA - X3, ALTURA,
             "Indicador de Operação / Código IBGE Incidência / Município Incidência / Sigla UF", "- / - / - / -")
    r.y += ALTURA
    r._campo(X1, LARG_COL, ALTURA, "Exclusões e Reduções da Base de Cálculo", "R$ 0,00")
    r._campo(X2, LARG_COL, ALTURA, "Base de Cálculo Após Exclusões e Reduções", "-")
    r._campo(X3, LARG_COL, ALTURA, "Red. Alíquota IBS / Red. Alíquota CBS", "- / - / -")
    r._campo(X4, DIREITA - X4, ALTURA, "Alíquota - IBS UF / IBS Mun", "- / -")
    r.y += ALTURA
    r._campo(X1, LARG_COL, ALTURA, "Alíq. Efetiva Municipal - IBS", "-")
    r._campo(X2, LARG_COL, ALTURA, "Valor Apurado Municipal - IBS", "-")
    r._campo(X3, LARG_COL, ALTURA, "Alíq. Efetiva Estadual - IBS", "-")
    r._campo(X4, DIREITA - X4, ALTURA, "Valor Apurado Estadual - IBS", "-")
    r.y += ALTURA
    r._campo(X1, LARG_COL, ALTURA, "Valor Total Apurado - IBS", "-")
    r._campo(X2, LARG_COL, ALTURA, "Alíquota - CBS", "-")
    r._campo(X3, LARG_COL, ALTURA, "Alíquota Efetiva - CBS", "-")
    r._campo(X4, DIREITA - X4, ALTURA, "Valor Total Apurado - CBS", "-")
    r.y += ALTURA
    r.linha_divisoria()

    # ---- Valor Total da NFS-e (item 2.1.11) -------------------------------
    v_serv = _t(inf_dps, "valores/vServPrest/vServ")
    v_liq = _t(inf_nfse, "valores/vLiq")
    # Rótulos em maiúsculas só nos 3 campos de valor "grandes" (Valor da
    # Operação/Serviço, Valor Líquido da NFS-e, Valor Líquido + IBS/CBS) --
    # os demais (Desconto.../Total.../Total do IBS-CBS) ficam em texto
    # normal, exatamente como o DANFSe real (conferido campo a campo).
    r._titulo_bloco("VALOR TOTAL DA NFS-e", ALTURA)
    r._campo(X2, LARG_COL, ALTURA, "Valor da Operação / Serviço", _moeda(v_serv), label_maiusculo=True)
    r._campo(X3, LARG_COL, ALTURA, "Desconto Incondicionado", "-")
    r._campo(X4, DIREITA - X4, ALTURA, "Desconto Condicionado", "-")
    r.y += ALTURA
    r._campo(X1, LARG_COL, ALTURA, "Total das Retenções (ISSQN / Federais)", "-")
    r._campo(X2, LARG_COL, ALTURA, "Valor Líquido da NFS-e", _moeda(v_liq), label_maiusculo=True)
    r._campo(X3, LARG_COL, ALTURA, "Total do IBS/CBS", "R$ 0,00")
    r._campo(X4, DIREITA - X4, ALTURA, "Valor Líquido da NFS-e + IBS/CBS", "R$ 0,00", sombreado=True,
             label_maiusculo=True)
    r.y += ALTURA
    r.linha_divisoria()

    # ---- Informações Complementares (item 2.1.12) -- texto literal do
    # DANFSe oficial (confirmado contra as NFS-e 30 e 31) -- nunca substituído
    # por um cálculo próprio (ex.: percentual do Simples Nacional), que seria
    # inventar dado tributário que a NFS-e não trouxe.
    partes_info = ["Totais aproximados dos Tributos cfe. Lei n° 12.741/2012: Federais: -; Estaduais: -; "
                   "Municipais: -;"]
    substituida = _t(inf_dps, "subst/chSubstda")
    if substituida:
        partes_info.insert(0, f"NFS-e Subst.: {substituida}")
    texto_info = " | ".join(partes_info)
    r._texto(X1, r.y + 0.06 + 3.8 / PT_PER_CM, "INFORMAÇÕES COMPLEMENTARES", _FONTE_TITULO, 7, largura_cm=LARG_TOTAL)
    r.y += GAP_APOS_TITULO_INFO + (3.8 + 1.8) / PT_PER_CM
    for k, linha_info in enumerate(_quebrar(texto_info, _cm(LARG_TOTAL) - 6, _FONTE_CONTEUDO, 7, 3)):
        r._texto(X1, r.y + k * 0.30, linha_info, _FONTE_CONTEUDO, 7, largura_cm=LARG_TOTAL)

    # ---- Canhoto (opcional, item 2.1.13) -- fixado perto do rodapé, como no
    # DANFSe real (o espaço entre Informações Complementares e o Canhoto fica
    # em branco quando o conteúdo é curto -- item 12 da revisão de layout).
    # Colunas medidas no PDF real: 1ª e 2ª col. = largura de 1 coluna da
    # grade principal cada; 3ª col. (Nº/Chave) = as outras 2 colunas juntas,
    # senão a chave completa não cabe e é truncada.
    y_canhoto = 28.05
    altura_canhoto = 20.1 / PT_PER_CM
    x_canhoto = [X1, X2, X3]
    larguras_canhoto = [X2 - X1, X3 - X2, DIREITA - X3]
    c.setLineWidth(0.5)
    c.setStrokeColor(_PRETO)
    c.rect(_cm(X1), _y(y_canhoto + altura_canhoto), _cm(LARG_TOTAL), _cm(altura_canhoto), fill=0)
    for x in x_canhoto[1:]:
        c.line(_cm(x), _y(y_canhoto), _cm(x), _y(y_canhoto + altura_canhoto))
    r.y = y_canhoto
    r._campo(x_canhoto[0], larguras_canhoto[0], altura_canhoto, "Data Cientificação:", "", label_maiusculo=True)
    r._campo(x_canhoto[1], larguras_canhoto[1], altura_canhoto, "Identificação e Assinatura", "",
             label_maiusculo=True)
    r._campo(x_canhoto[2], larguras_canhoto[2], altura_canhoto, "N° NFS-e / Chave NFS-e",
             f"{_t(inf_nfse, 'nNFSe') or '-'} / {chave}", label_maiusculo=True)

    # ---- Marca d'água de cancelamento/substituição (itens 2.5.1/2.5.2) -----
    if marca_dagua:
        c.saveState()
        c.setFont(_FONTE_TITULO_REGULAR, 60)
        c.setFillColor(colors.Color(0.35, 0.35, 0.35, alpha=0.35))
        c.translate(PAGE_W / 2, PAGE_H / 2)
        c.rotate(45)
        c.drawCentredString(0, 0, marca_dagua)
        c.restoreState()

    c.showPage()
    c.save()
    saida.seek(0)
    return saida.read()


def gerar_danfse_para_registro(xml_nfse: str, status: str) -> bytes:
    """Igual a `gerar_danfse_pdf`, mas aplica a marca d'água de CANCELADA
    quando o registro (nosso, não o XML) está marcado como cancelado --
    itens 2.5.1/2.5.2 da NT."""
    marca_dagua = "CANCELADA" if status in ("cancelado", "cancelada") else None
    return gerar_danfse_pdf(xml_nfse, marca_dagua)


# Layout padrão: v1.0, idêntico ao PDF do Portal Nacional/Prefeitura de BH que a JL já usa (danfse_v1.py).
# O motor v2.0 (NT 008/2026) continua disponível em `gerar_danfse_pdf_v2`.
LAYOUT_PADRAO = os.environ.get("NFSE_DANFSE_LAYOUT", "v1")


def gerar_danfse_pdf(xml_nfse: str, marca_dagua: str | None = None) -> bytes:
    if LAYOUT_PADRAO == "v2":
        return gerar_danfse_pdf_v2(xml_nfse, marca_dagua)
    from . import danfse_v1
    return danfse_v1.gerar_danfse_pdf(xml_nfse, marca_dagua)
