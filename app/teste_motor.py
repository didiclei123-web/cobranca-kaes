"""
Teste do passo a passo completo com um navegador SIMULADO (sem internet).
Reproduz os casos reais: pago, pago no cartão, vencido, porcentagem, nome diferente,
cliente sem cobrança na data, cliente não encontrado.
"""
import json
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

# usa uma pasta temporária como "pasta do programa"
TMP = Path(tempfile.mkdtemp())
for f in ("config.json", "mapa_asaas.json"):
    shutil.copy(Path(__file__).parent / f, TMP / f)
sys.path.insert(0, str(Path(__file__).parent))
import base  # noqa: E402

base.DADOS = TMP
base.ARQ_CONFIG, base.ARQ_MAPA, base.ARQ_ESTADO = TMP / "config.json", TMP / "mapa_asaas.json", TMP / "estado.json"
base.PASTA_RELATORIOS = TMP / "relatorios"
cfg = json.loads(base.ARQ_CONFIG.read_text(encoding="utf-8"))
cfg["clickup_url_lista"] = "https://app.clickup.com/x"
base.salvar_config(cfg)
base.salvar_texto_mapa(json.dumps({"Lucas show premiações": "Lucas Andrade de Sousa"}))

import motor  # noqa: E402
import regras as R  # noqa: E402

motor.ARQ_ESTADO, motor.PASTA_RELATORIOS = base.ARQ_ESTADO, base.PASTA_RELATORIOS
HOJE = R.hoje()
D = lambda n: HOJE - timedelta(days=n)  # noqa: E731

TAREFAS = [  # nome, status, vencimento, porcentagem, status_pagamento
    ("Sortudo da Rifa - Marcos Dantas", "renovação encaminhada", D(12), "", "PAGO"),
    ("Paulo Vítor Souza Lima - Paulo Som", "para renovar", D(7), "", "PAGO"),
    ("Zeca Premios - Davi Alves Barros", "para renovar", D(38), "", "INADIMPLENTE"),
    ("[Luiz Augusto] Mateus Moura Viana [Mensalista]", "para renovar", D(7), "", "INADIMPLENTE"),
    ("Lucas show premiações", "mensalistas - ativos", D(2), "", "PAGO"),
    ("XyzPremios - Anderson Silva Gomes", "mensalistas - ativos", D(7), "", "PAGO"),
    ("Campeões da Pista - Daniel Alves de Souza Filho", "mensalistas - ativos", D(12), "SIM", "PAGO"),
    ("ABPremiações - Leandro Lopes", "mensalistas - ativos", HOJE + timedelta(days=13), "SIM", "PAGO"),
    ("Fulano Premios", "mensalistas - ativos", None, "", ""),
    ("Ciclano Premiacoes", "pausado", D(30), "", "PAGO"),  # status fora do alvo
]
# cliente no Asaas, valor, vencimento, situação
ASAAS = [
    ("ALFA PROMOCOES LTDA - Sortudo/Sortudo - Marcos", "R$ 4.000,00", D(12), "Vencida"),
    ("ALFA PROMOCOES LTDA - Sortudo/Sortudo - Marcos", "R$ 4.000,00", D(-18), "Aguardando pagamento"),
    ("PAULOSOM PRODUCOES LTDA", "R$ 3.000,00", D(7), "Recebida"),
    ("DAVI ALVES BARROS", "R$ 2.263,79", D(38), "Confirmada"),
    ("MATEUS MOURA VIANA", "R$ 2.500,00", D(17), "Vencida"),
    ("LUCAS ANDRADE DE SOUSA", "R$ 4.000,00", D(2), "Recebida"),
    ("FRANCISCO LUCAS ALVES DE ASSIS", "R$ 4.500,00", D(-3), "Aguardando pagamento"),
]


class NavFalso:
    canal = "simulado"

    def __init__(self):
        self.alteracoes = []

    def login_clickup(self): pass
    def login_asaas(self): pass

    def listar_tarefas_clickup(self, status_alvo):
        alvo = {R.sem_acento(s) for s in status_alvo}
        return [{"nome": n, "url": f"https://app.clickup.com/t/{i}", "status": s}
                for i, (n, s, *_r) in enumerate(TAREFAS) if R.sem_acento(s) in alvo]

    def ler_tarefa(self, url):
        n, s, v, p, sp = TAREFAS[int(url.rsplit("/", 1)[1])]
        return {"vencimento": v, "porcentagem": p, "status_pagamento": sp}

    def buscar_cobrancas(self, termo):
        t = R.sem_acento(termo)
        return [{"indice": i, "cliente": c, "valor": v, "descricao": "", "vencimento": d, "icones": [],
                 "termo": termo, "url_busca": "busca:" + termo}
                for i, (c, v, d, s) in enumerate(ASAAS) if t in R.sem_acento(c)]

    def detalhar_cobranca(self, linha):
        c, v, d, s = next(x for x in ASAAS if x[0] == linha["cliente"] and x[2] == linha["vencimento"])
        return {"situacao": s, "cliente": c, "link": f"https://www.asaas.com/i/{abs(hash((c, d))) % 10**8}",
                "url_cobranca": "show"}

    def alterar_tarefa(self, url, nova_data=None, marcar_pago=False):
        self.alteracoes.append((url, nova_data, marcar_pago))
        return []


def checar(cond, msg):
    print(("OK   " if cond else "FALHOU ") + msg)
    assert cond, msg


nav = NavFalso()
avisos = []
estado = motor.conferir(nav, avisar=avisos.append)
por_nome = {r["nome"]: r for r in estado["resultados"]}

checar(por_nome["Sortudo da Rifa - Marcos Dantas"]["classificacao"] == "inadimplente", "Sortudo = inadimplente")
checar(por_nome["Paulo Vítor Souza Lima - Paulo Som"]["classificacao"] == "pago", "Paulo (PAULOSOM) = pago")
checar(por_nome["Zeca Premios - Davi Alves Barros"]["classificacao"] == "pago", "Zeca (cartão confirmado) = pago")
checar(por_nome["[Luiz Augusto] Mateus Moura Viana [Mensalista]"]["busca"] == "sem_data", "Mateus = sem cobrança na data")
checar(por_nome["Lucas show premiações"]["classificacao"] == "pago", "Lucas show (via mapa) = pago")
checar(por_nome["XyzPremios - Anderson Silva Gomes"]["classificacao"] == "nao_encontrado", "Anderson = não encontrado")
checar([p["nome"] for p in estado["porcentagem"]] == ["Campeões da Pista - Daniel Alves de Souza Filho"],
       "porcentagem: só o vencido entra")
checar("Ciclano Premiacoes" not in por_nome, "status fora do alvo é ignorado")
checar(estado["sem_data"] == ["Fulano Premios"], "tarefa sem data listada à parte")
checar(any(p.name.startswith("relatorio_") for p in base.PASTA_RELATORIOS.iterdir()), "relatório salvo")

msgs = motor.mensagens_inadimplentes(estado)
checar(len(msgs) == 1 and msgs[0][1].startswith("Olá, Marcos!") and "asaas.com/i/" in msgs[0][1],
       "mensagem do Marcos com link")
checar(R.data_br(D(12)) in msgs[0][1], "mensagem tem a data certa")

plano = motor.plano_atualizacao(estado)
nomes = sorted(p["nome"] for p in plano)
checar(nomes == sorted(["Paulo Vítor Souza Lima - Paulo Som", "Zeca Premios - Davi Alves Barros",
                        "Lucas show premiações", "Campeões da Pista - Daniel Alves de Souza Filho"]),
       f"plano de atualização: {nomes}")
pablo = next(p for p in plano if p["nome"].startswith("Paulo"))
checar(pablo["nova_data"] == R.data_br(R.mais_um_mes(D(7))), "nova data = +1 mês")

motor.aplicar(nav, estado, plano)
checar(len(nav.alteracoes) == 4 and all(a[2] for a in nav.alteracoes), "4 tarefas alteradas, todas PAGO")
checar(motor.plano_atualizacao(motor.carregar_estado()) == [], "não altera de novo a mesma tarefa")

linhas = motor.buscar_cobrancas_cliente(nav, "Marcos")
vencida = next(l for l in linhas if l["vencimento"] == D(12))
sit, msg = motor.mensagem_da_cobranca(nav, "Marcos", vencida)
checar(sit == "Vencida" and msg.startswith("Olá, Marcos!"), "mensagem avulsa para cliente")
sit, msg = motor.mensagem_da_cobranca(nav, "Marcos", vencida, data_original="20/11/2026", sem_juros=True)
checar("sem cobrança de juros" in msg and "20/11/2026" in msg and R.data_br(D(12)) in msg, "mensagem sem juros")

shutil.rmtree(TMP, ignore_errors=True)
print("\nTodos os testes do motor passaram.")
