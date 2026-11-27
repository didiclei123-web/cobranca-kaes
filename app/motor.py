"""
O "motor": o passo a passo da conferência, das mensagens e das atualizações.
Não sabe nada de janela; recebe funções para avisar o andamento.
"""
import json
from datetime import datetime

import regras as R
from base import ARQ_ESTADO, PASTA_RELATORIOS, carregar_config, carregar_mapa

DICAS_ICONE = {"check-filled": "paga", "x-filled": "vencida", "clock-filled": "aguardando / cartão"}


def agora_txt():
    return datetime.now().strftime("%Y-%m-%d_%H%M")


def salvar_texto(texto, prefixo):
    PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)
    arq = PASTA_RELATORIOS / f"{prefixo}_{agora_txt()}.txt"
    arq.write_text(texto, encoding="utf-8")
    return arq


def salvar_estado(estado):
    ARQ_ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")


def carregar_estado():
    if not ARQ_ESTADO.exists():
        return None
    return json.loads(ARQ_ESTADO.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ Asaas
def localizar_no_asaas(nav, nome_clickup, vencimento, mapa):
    vistos, linhas = set(), []

    def juntar(novas):
        for l in novas:
            chave = (R.sem_acento(l["cliente"]), l["vencimento"], l["valor"], l["descricao"])
            if chave not in vistos:
                vistos.add(chave)
                l["reserva"] = False
                linhas.append(l)

    for termo in R.termos_de_busca(nome_clickup, mapa):
        juntar(nav.buscar_cobrancas(termo))
        status, dados = R.escolher_cobranca(linhas, vencimento)
        if status == "ok":
            return status, dados
    status, dados = R.escolher_cobranca(linhas, vencimento)
    if status in ("nao_encontrado", "sem_data"):
        reserva, vistos_reserva = [], set()
        for palavra in R.palavras_reserva(nome_clickup):
            for l in nav.buscar_cobrancas(palavra):
                chave = (R.sem_acento(l["cliente"]), l["vencimento"], l["valor"], l["descricao"])
                if l["vencimento"] == vencimento and chave not in vistos_reserva:
                    vistos_reserva.add(chave)
                    l["reserva"] = True
                    reserva.append(l)
        st2, d2 = R.escolher_cobranca(reserva, vencimento)
        if st2 in ("ok", "ambiguo"):
            return st2, d2
    return status, dados


# ------------------------------------------------------------------ 1. Conferir
def conferir(nav, avisar=print, progresso=lambda atual, total, texto: None):
    cfg, mapa = carregar_config(), carregar_mapa()
    status_alvo = cfg["status_alvo"]
    dia = R.hoje()

    avisar("Lendo a lista do ClickUp...")
    nav.login_clickup()
    tarefas = nav.listar_tarefas_clickup(status_alvo)
    avisar(f"{len(tarefas)} tarefas nos status escolhidos.")

    vencidos, porcentagem, sem_data = [], [], []
    for i, t in enumerate(tarefas, 1):
        progresso(i, len(tarefas) * 2, f"ClickUp: {t['nome']}")
        try:
            t.update(nav.ler_tarefa(t["url"]))
        except Exception as e:
            avisar(f"! Falha ao ler '{t['nome']}': {e}")
            continue
        if not t["vencimento"]:
            sem_data.append(t)
        elif t["vencimento"] < dia:
            (porcentagem if R.sem_acento(t["porcentagem"]) == "sim" else vencidos).append(t)

    avisar(f"{len(vencidos)} vencidos para conferir no Asaas, {len(porcentagem)} de porcentagem.")
    nav.login_asaas()
    resultados = []
    for i, t in enumerate(vencidos, 1):
        progresso(len(tarefas) + int(i * len(tarefas) / max(len(vencidos), 1)), len(tarefas) * 2,
                  f"Asaas: {t['nome']}")
        venc = t["vencimento"]
        try:
            st, linhas = localizar_no_asaas(nav, t["nome"], venc, mapa)
        except Exception as e:
            avisar(f"! Falha no Asaas para '{t['nome']}': {e}")
            st, linhas = "nao_encontrado", []
        r = {"nome": t["nome"], "url": t["url"], "status_clickup": t["status"],
             "vencimento": R.data_br(venc), "status_pagamento_clickup": t.get("status_pagamento", ""),
             "busca": st, "cobrancas": [], "classificacao": None, "confirmar_nome": False, "detalhe": []}
        if st == "ok":
            for l in linhas:
                det = nav.detalhar_cobranca(l)
                r["cobrancas"].append({"cliente": det.get("cliente") or l["cliente"], "valor": l["valor"],
                                       "situacao": det["situacao"], "link": det["link"],
                                       "url": det.get("url_cobranca", "")})
                r["confirmar_nome"] = r["confirmar_nome"] or l.get("reserva", False)
            classes = [R.classificar_situacao(c["situacao"]) for c in r["cobrancas"]]
            r["classificacao"] = ("inadimplente" if "inadimplente" in classes else
                                  "pago" if classes and all(c == "pago" for c in classes) else
                                  classes[0] if classes else "outro")
        else:
            r["classificacao"] = "nao_encontrado"
            r["detalhe"] = [f"{l['cliente']} — {R.data_br(l['vencimento']) if l['vencimento'] else '?'} — {l['valor']}"
                            for l in linhas][:8]
        avisar(f"{t['nome']} → {r['classificacao']}")
        resultados.append(r)

    estado = {
        "data": R.data_br(dia), "gerado_em": agora_txt(), "resultados": resultados,
        "porcentagem": [{"nome": t["nome"], "url": t["url"], "vencimento": R.data_br(t["vencimento"]),
                         "status_clickup": t["status"],
                         "status_pagamento_clickup": t.get("status_pagamento", "")} for t in porcentagem],
        "sem_data": [t["nome"] for t in sem_data], "atualizados": [],
    }
    salvar_estado(estado)
    arq = salvar_texto(relatorio_texto(estado), "relatorio")
    progresso(1, 1, "Conferência concluída")
    avisar(f"Relatório salvo em {arq}")
    return estado


MOTIVOS = {"sem_data": "cliente achado, mas sem cobrança nessa data",
           "ambiguo": "mais de um cliente com cobrança nessa data",
           "nao_encontrado": "nenhuma cobrança encontrada"}


def relatorio_texto(estado):
    res = estado["resultados"]
    out = [f"RELATÓRIO DE COBRANÇAS — {estado['data']}", "=" * 56]

    def bloco(titulo, itens, fmt):
        out.append(f"\n{titulo} ({len(itens)})")
        out.extend(fmt(x) for x in itens) if itens else out.append("  —")

    def cob(r):
        c = "; ".join(f"{x['situacao']} {x['valor']} ({x['cliente']})" for x in r["cobrancas"])
        return f"  • {r['nome']} — venc. {r['vencimento']} — {c}" + ("  [CONFIRMAR NOME]" if r["confirmar_nome"] else "")

    bloco("INADIMPLENTES", [r for r in res if r["classificacao"] == "inadimplente"], cob)
    bloco("PAGOS", [r for r in res if r["classificacao"] == "pago"], cob)
    bloco("AGUARDANDO / OUTROS", [r for r in res if r["classificacao"] in ("aguardando", "outro")], cob)
    bloco("NÃO ENCONTRADOS NO ASAAS", [r for r in res if r["classificacao"] == "nao_encontrado"],
          lambda r: f"  • {r['nome']} — venc. {r['vencimento']} — {MOTIVOS.get(r['busca'], r['busca'])}"
                    + "".join(f"\n      - {d}" for d in r.get("detalhe", [])))
    bloco("PORCENTAGEM = SIM (não conferidos no Asaas)", estado["porcentagem"],
          lambda p: f"  • {p['nome']} — venc. {p['vencimento']}")
    if estado.get("sem_data"):
        bloco("SEM DATA DE VENCIMENTO", estado["sem_data"], lambda n: f"  • {n}")
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ 2. Mensagens
def mensagens_inadimplentes(estado):
    """Lista de (nome_clickup, texto_mensagem)."""
    cfg = carregar_config()
    saida = []
    for r in estado["resultados"]:
        if r["classificacao"] != "inadimplente":
            continue
        for c in r["cobrancas"]:
            if R.classificar_situacao(c["situacao"]) == "inadimplente":
                saida.append((r["nome"], R.montar_mensagem(cfg["modelo_mensagem"], R.primeiro_nome(r["nome"]),
                                                           r["vencimento"], c["link"] or "(link não encontrado)")))
    return saida


# ------------------------------------------------------------------ 3. Atualizar
def plano_atualizacao(estado):
    """Itens que podem ser atualizados: pagos + porcentagem ainda não atualizados."""
    feitos = set(estado.get("atualizados", []))
    plano = []
    for r in estado["resultados"]:
        if r["classificacao"] == "pago" and r["url"] not in feitos:
            plano.append({"nome": r["nome"], "url": r["url"], "motivo": "pago", "vencimento": r["vencimento"]})
    for p in estado["porcentagem"]:
        if p["url"] not in feitos:
            plano.append({"nome": p["nome"], "url": p["url"], "motivo": "porcentagem", "vencimento": p["vencimento"]})
    for item in plano:
        item["nova_data"] = R.data_br(R.mais_um_mes(R.ler_data(item["vencimento"])))
    return plano


def aplicar(nav, estado, itens, ao_terminar_item=lambda item, problemas: None):
    nav.login_clickup()
    for item in itens:
        try:
            problemas = nav.alterar_tarefa(item["url"], R.ler_data(item["nova_data"]), marcar_pago=True)
        except Exception as e:
            problemas = [str(e)]
        if not problemas:
            estado.setdefault("atualizados", []).append(item["url"])
            salvar_estado(estado)
        ao_terminar_item(item, problemas)


# ------------------------------------------------------------------ 4. Mensagem para um cliente
def buscar_cobrancas_cliente(nav, cliente):
    mapa = carregar_mapa()
    termos = [cliente]
    for nome_ck, valor in mapa.items():
        if R.sem_acento(cliente) in R.sem_acento(nome_ck):
            termos = (valor if isinstance(valor, list) else [valor]) + termos
    nav.login_asaas()
    linhas, vistos = [], set()
    for termo in termos:
        for l in nav.buscar_cobrancas(termo):
            chave = (l["cliente"], l["vencimento"], l["valor"])
            if chave not in vistos:
                vistos.add(chave)
                l["dica"] = next((DICAS_ICONE[x] for x in l["icones"] if x in DICAS_ICONE), "outra")
                linhas.append(l)
        if linhas:
            break
    linhas.sort(key=lambda l: l["vencimento"] or R.hoje(), reverse=True)
    return linhas


def mensagem_da_cobranca(nav, cliente, linha, data_original=None, sem_juros=False):
    cfg = carregar_config()
    det = nav.detalhar_cobranca(linha)
    nome = R.primeiro_nome(cliente)
    data_cob = R.data_br(linha["vencimento"])
    link = det["link"] or "(link não encontrado)"
    if sem_juros and data_original:
        msg = R.montar_mensagem(cfg["modelo_mensagem_sem_juros"], nome, data_original, link, nova_data=data_cob)
    else:
        msg = R.montar_mensagem(cfg["modelo_mensagem"], nome, data_cob, link)
    salvar_texto(msg, "mensagem_" + R.sem_acento(nome).replace(" ", "_"))
    return det["situacao"], msg
