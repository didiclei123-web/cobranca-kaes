"""
Regras de negócio (sem navegador): datas, nomes, correspondência ClickUp x Asaas,
mensagens e interpretação de comandos por palavras-chave.
Tudo aqui pode ser testado sem internet.
"""
import calendar
import re
import unicodedata
from datetime import date, datetime

# Palavras que aparecem em muitos nomes e não ajudam a achar o cliente no Asaas
PALAVRAS_GENERICAS = {
    "premios", "premio", "premiacoes", "premiacao", "rifa", "rifas", "acoes", "acao",
    "sorte", "sorteio", "sorteios", "mensalista", "asaas", "ltda", "the", "dos", "das",
    "de", "da", "do", "e", "loco", "brasil", "oficial",
}

SITUACOES_PAGAS = {"recebida", "confirmada", "recebida em dinheiro"}
SITUACOES_VENCIDAS = {"vencida"}


# ----------------------------------------------------------------- texto
def sem_acento(txt: str) -> str:
    txt = unicodedata.normalize("NFKD", txt or "")
    return "".join(c for c in txt if not unicodedata.combining(c)).lower().strip()


# ----------------------------------------------------------------- datas
def ler_data(txt: str):
    """Aceita dd/mm/aa, dd/mm/aaaa ou d/m/aa. Retorna date ou None."""
    if not txt:
        return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", txt)
    if not m:
        return None
    d, mth, y = (int(x) for x in m.groups())
    if y < 100:
        y += 2000
    try:
        return date(y, mth, d)
    except ValueError:
        return None


def data_br(d: date, ano_curto=False) -> str:
    return d.strftime("%d/%m/%y" if ano_curto else "%d/%m/%Y")


def mais_um_mes(d: date) -> date:
    """Mesmo dia no mês seguinte (31/01 -> 28 ou 29/02)."""
    ano = d.year + (1 if d.month == 12 else 0)
    mes = 1 if d.month == 12 else d.month + 1
    ultimo = calendar.monthrange(ano, mes)[1]
    return date(ano, mes, min(d.day, ultimo))


def hoje() -> date:
    return datetime.now().date()


# ----------------------------------------------------------------- nomes
def termos_de_busca(nome_clickup: str, mapa: dict) -> list:
    """
    Gera, em ordem de confiança, os termos para pesquisar o cliente no Asaas.
    1) mapa_asaas.json (você controla)  2) '(ASAAS: X)' e '[X]' no nome
    3) partes separadas por ' - ' ou '/'.
    """
    termos = []
    if nome_clickup in mapa and mapa[nome_clickup]:
        valor = mapa[nome_clickup]
        termos.extend(valor if isinstance(valor, list) else [valor])

    m = re.search(r"\(\s*asaas\s*:\s*([^)]+)\)", nome_clickup, flags=re.I)
    if m:
        termos.append(m.group(1).strip())
    for colchete in re.findall(r"\[([^\]]+)\]", nome_clickup):
        if sem_acento(colchete) not in {"mensalista", "a vista + parcelado"}:
            termos.append(colchete.strip())

    limpo = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", nome_clickup)
    for parte in re.split(r"\s+-\s+|/", limpo):
        parte = re.sub(r"\s+", " ", parte).strip(" -@")
        if len(parte) >= 3 and sem_acento(parte) not in PALAVRAS_GENERICAS:
            termos.append(parte)

    vistos, saida = set(), []
    for t in termos:
        k = sem_acento(t)
        if k and k not in vistos:
            vistos.add(k)
            saida.append(t)
    return saida


def palavras_reserva(nome_clickup: str) -> list:
    """Última tentativa: palavras soltas (resultado marcado como 'confirmar')."""
    limpo = re.sub(r"\([^)]*\)|\[[^\]]*\]|@\S+", " ", nome_clickup)
    palavras = re.findall(r"[A-Za-zÀ-ÿ]{4,}", limpo)
    saida = []
    for p in palavras:
        if sem_acento(p) not in PALAVRAS_GENERICAS and p not in saida:
            saida.append(p)
    return saida


def primeiro_nome(nome_clickup: str) -> str:
    """'Sortudo da Rifa - Marcos Dantas' -> 'Marcos'."""
    m = re.search(r"\(\s*asaas\s*:\s*([^)]+)\)", nome_clickup, flags=re.I)
    base = m.group(1) if m else re.split(r"\s+-\s+", re.sub(r"\[[^\]]*\]", "", nome_clickup))[-1]
    base = re.sub(r"\([^)]*\)", "", base)
    palavras = re.findall(r"[A-Za-zÀ-ÿ]+", base)
    return palavras[0].capitalize() if palavras else nome_clickup.strip()


def classificar_situacao(situacao: str) -> str:
    s = sem_acento(situacao)
    if s in SITUACOES_PAGAS or s.startswith("recebida") or s.startswith("confirmada"):
        return "pago"
    if s in SITUACOES_VENCIDAS:
        return "inadimplente"
    if s.startswith("aguardando"):
        return "aguardando"
    return "outro"


def escolher_cobranca(linhas: list, data_alvo: date):
    """
    linhas: [{'cliente','valor','descricao','vencimento'(date),'termo','reserva'(bool)}]
    Retorna (status, dados): status em {'ok','ambiguo','sem_data','nao_encontrado'}.
    """
    if not linhas:
        return "nao_encontrado", []
    na_data = [l for l in linhas if l["vencimento"] == data_alvo]
    if not na_data:
        return "sem_data", linhas
    clientes = {}
    for l in na_data:
        clientes.setdefault(sem_acento(l["cliente"]), []).append(l)
    if len(clientes) == 1:
        return "ok", na_data
    return "ambiguo", na_data


# ----------------------------------------------------------------- mensagens
def montar_mensagem(modelo: str, nome: str, data_txt: str, link: str, nova_data: str = "") -> str:
    return (modelo.replace("[NOME DO CLIENTE]", nome)
                  .replace("[DATA DE VENCIMENTO]", data_txt)
                  .replace("[NOVA DATA]", nova_data)
                  .replace("[LINK DE COBRANÇA]", link))


# ----------------------------------------------------------------- comandos
ACOES = ["conferir", "mensagens", "atualizar", "mensagem_cliente", "ajuda", "sair"]


def interpretar_palavras_chave(texto: str) -> dict:
    """Entende comandos sem IA. Funciona com números do menu ou frases simples."""
    t = sem_acento(texto)
    r = {"acao": None, "cliente": None, "data_original": None, "sem_juros": False}
    numeros = {"1": "conferir", "2": "mensagens", "3": "atualizar",
               "4": "mensagem_cliente", "5": "ajuda", "0": "sair"}
    if t in numeros:
        r["acao"] = numeros[t]
        return r
    if re.search(r"\b(sair|fechar|encerrar|tchau)\b", t):
        r["acao"] = "sair"
    elif re.search(r"\b(ajuda|help|comandos|o que (voce|vc) faz)\b", t):
        r["acao"] = "ajuda"
    elif re.search(r"\b(atualiz|altera|marca|coloca|muda|empurra)", t) and re.search(
            r"\b(pago|pagos|data|vencimento|porcentagem|clickup)", t):
        r["acao"] = "atualizar"
    elif re.search(r"\b(mensage(m|ns)|cobra|lembrete|texto)", t):
        m = re.search(r"\b(?:para|pra|pro|ao)\s+(?:o |a )?([a-z0-9 ]{3,40}?)(?:,|\.|$| que | com | venc| sem )", t + " ")
        if m and not re.search(r"\b(todos|inadimplentes|vencidos|cobranca|cobrancas|clientes|eles|cada)\b",
                               m.group(1)):
            r["acao"] = "mensagem_cliente"
            r["cliente"] = m.group(1).strip()
        else:
            r["acao"] = "mensagens"
    elif re.search(r"\b(confer|verific|checa|analis|quem (pagou|nao pagou|deve)|vencid|inadimpl|relatorio|lista)", t):
        r["acao"] = "conferir"
    d = ler_data(texto)
    if d:
        r["data_original"] = data_br(d)
    r["sem_juros"] = bool(re.search(r"sem juros", t))
    return r
