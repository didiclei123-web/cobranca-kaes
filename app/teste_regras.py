"""Testes das regras (rode com: python teste_regras.py). Não precisa de internet."""
from datetime import date

import regras as R

MAPA = {"Lucas show premiações": "Lucas Andrade de Sousa"}


def checar(cond, msg):
    print(("OK   " if cond else "FALHOU ") + msg)
    assert cond, msg


# datas
checar(R.ler_data("20/11/26") == date(2026, 11, 20), "lê dd/mm/aa")
checar(R.ler_data("5/12/2026") == date(2026, 12, 5), "lê d/mm/aaaa")
checar(R.ler_data("há 2 dias") is None, "ignora texto relativo")
checar(R.mais_um_mes(date(2026, 11, 20)) == date(2026, 12, 20), "+1 mês normal")
checar(R.mais_um_mes(date(2026, 12, 15)) == date(2027, 1, 15), "+1 mês virando o ano")
checar(R.mais_um_mes(date(2027, 1, 31)) == date(2027, 2, 28), "+1 mês em dia 31")

# nomes / termos
t = R.termos_de_busca("[Luiz Augusto] Moto Show Elias (ASAAS: Luiz Augusto)", {})
checar(t[0] == "Luiz Augusto" and "Moto Show Elias" in t, f"termos com ASAAS/colchete: {t}")
t = R.termos_de_busca("Sortudo da Rifa - Marcos Dantas", {})
checar(t == ["Sortudo da Rifa", "Marcos Dantas"], f"termos por partes: {t}")
t = R.termos_de_busca("Lucas show premiações", MAPA)
checar(t[0] == "Lucas Andrade de Sousa", f"mapa tem prioridade: {t}")
t = R.termos_de_busca("[Luiz Augusto] Mateus Moura Viana [Mensalista]", {})
checar("Mensalista" not in t and "Mateus Moura Viana" in t, f"ignora [Mensalista]: {t}")
checar(R.palavras_reserva("Lucas show premiações") == ["Lucas", "show"], "palavras reserva sem genéricas")

checar(R.primeiro_nome("Sortudo da Rifa - Marcos Dantas") == "Marcos", "primeiro nome Marcos")
checar(R.primeiro_nome("Pedrinho Bento - Pedro Bento") == "Pedro", "primeiro nome Pedro")
checar(R.primeiro_nome("XyzPremios - Anderson Silva Gomes") == "Anderson", "primeiro nome Anderson")
checar(R.primeiro_nome("[Luiz Augusto] Moto Show Elias (ASAAS: Luiz Augusto)") == "Luiz", "primeiro nome via ASAAS")
checar(R.primeiro_nome("Lucas show premiações") == "Lucas", "primeiro nome nome único")

# situações
checar(R.classificar_situacao("Vencida") == "inadimplente", "Vencida -> inadimplente")
checar(R.classificar_situacao("Confirmada") == "pago", "Confirmada (cartão) -> pago")
checar(R.classificar_situacao("Recebida") == "pago", "Recebida -> pago")
checar(R.classificar_situacao("Aguardando pagamento") == "aguardando", "Aguardando")

# escolha de cobrança
L = lambda cli, d: {"cliente": cli, "vencimento": d, "valor": "R$ 1", "descricao": ""}
st, _ = R.escolher_cobranca([L("A", date(2026, 11, 20)), L("A", date(2026, 12, 20))], date(2026, 11, 20))
checar(st == "ok", "acha a cobrança na data")
st, _ = R.escolher_cobranca([L("MATEUS", date(2026, 11, 10))], date(2026, 11, 20))
checar(st == "sem_data", "cliente sem cobrança na data (caso Mateus)")
st, _ = R.escolher_cobranca([L("A", date(2026, 11, 25)), L("B", date(2026, 11, 25))], date(2026, 11, 25))
checar(st == "ambiguo", "dois clientes na mesma data -> ambíguo")
checar(R.escolher_cobranca([], date(2026, 1, 1))[0] == "nao_encontrado", "nada encontrado")

# mensagem
m = R.montar_mensagem("Olá, [NOME DO CLIENTE]! [DATA DE VENCIMENTO] [LINK DE COBRANÇA] [NOVA DATA]",
                      "Marcos", "15/11/2026", "https://x", "27/11/2026")
checar(m == "Olá, Marcos! 15/11/2026 https://x 27/11/2026", "preenche o modelo")

# comandos (sem IA)
P = R.interpretar_palavras_chave
checar(P("1")["acao"] == "conferir", "menu 1")
checar(P("confere quem não pagou")["acao"] == "conferir", "frase conferir")
checar(P("ve os vencidos de hoje")["acao"] == "conferir", "frase vencidos")
checar(P("gera as mensagens de cobrança")["acao"] == "mensagens", "frase mensagens")
c = P("faz uma mensagem para Anderson, venceu 20/11/2026 mas foi alterada sem juros")
checar(c["acao"] == "mensagem_cliente" and c["cliente"] == "anderson" and c["data_original"] == "20/11/2026"
       and c["sem_juros"], f"mensagem para cliente: {c}")
checar(P("marca os pagos e muda a data no clickup")["acao"] == "atualizar", "frase atualizar")
checar(P("sair")["acao"] == "sair", "sair")

print("\nTodos os testes passaram.")
