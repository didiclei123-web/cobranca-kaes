"""
Carrega a extensão num Chrome de verdade e deixa ela trabalhar nos sites falsos:
conferir -> mensagens -> atualizar (com digitação real da data) -> mensagem para cliente.
Uso: xvfb-run python testes-extensao/teste_extensao_chrome.py [caminho_do_chrome]
"""
import json
import shutil
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent))
import sites_falsos as SF  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
BASE = "http://localhost:8765"
falhas = []


def checar(cond, msg):
    print(("OK   " if cond else "FALHOU ") + msg, flush=True)
    if not cond:
        falhas.append(msg)


def estado_servidor():
    with urllib.request.urlopen(BASE + "/api/estado") as r:
        return json.load(r)


# cópia da extensão com permissão para os sites falsos
ext = Path(tempfile.mkdtemp()) / "extensao"
shutil.copytree(RAIZ / "extensao", ext)
man = json.loads((ext / "manifest.json").read_text(encoding="utf-8"))
man["host_permissions"].append("http://localhost:8765/*")
(ext / "manifest.json").write_text(json.dumps(man), encoding="utf-8")

SF.iniciar(8765)
chrome = sys.argv[1] if len(sys.argv) > 1 else None

with sync_playwright() as pw:
    opcoes = dict(headless=False, args=[f"--disable-extensions-except={ext}", f"--load-extension={ext}",
                                         "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
                                         "--disable-backgrounding-occluded-windows"])
    if chrome:
        opcoes["executable_path"] = chrome
    ctx = pw.chromium.launch_persistent_context(tempfile.mkdtemp(), **opcoes)
    sw = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker", timeout=20000)
    ext_id = sw.url.split("/")[2]
    print("extensão carregada:", ext_id)

    painel = ctx.new_page()
    erros = []
    painel.on("pageerror", lambda e: erros.append(str(e)))
    painel.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
    painel.on("dialog", lambda d: d.accept())  # confirma o "Alterar N tarefas?"
    painel.goto(f"chrome-extension://{ext_id}/painel.html")
    painel.wait_for_function("() => window.__painel !== undefined")
    checar("assistente de cobranças" in painel.inner_text("#chat"), "painel abre e cumprimenta")
    checar("Configurações" in painel.inner_text("#chat"), "pede o link na primeira vez")

    # configura pelo próprio formulário
    painel.click("#abas button[data-aba=config]")
    painel.fill("#cfgUrl", BASE + "/clickup/lista")
    painel.fill("#cfgAsaas", BASE)
    painel.fill("#cfgMapa", '"Lucas show premiações": "Lucas Andrade de Sousa",')
    painel.click("#salvarConfig")
    painel.wait_for_function("() => document.querySelector('#cfgAviso').textContent.includes('Salvo')")
    checar(True, "configurações salvas pelo formulário")

    # ---------------- conferir (pedido informal)
    painel.click("#abas button[data-aba=conversa]")
    painel.fill("#cmd", "e aí, quem tá devendo?")
    painel.press("#cmd", "Enter")
    painel.wait_for_function("() => window.__painel.S.ocupado === true", timeout=10000)
    try:
        painel.wait_for_function("() => window.__painel.S.ocupado === false", timeout=400000)
    except Exception:
        print("TIMEOUT. Abas:", [p.url for p in ctx.pages])
    print("---- CHAT ----\n" + painel.inner_text("#chat")[-2500:] + "\n--------------", flush=True)
    estado = painel.evaluate("window.__painel.S.estado")
    checar(estado is not None, "conferência terminou")
    por = {r["nome"]: r for r in (estado or {}).get("resultados", [])}
    checar(por.get("Sortudo da Rifa - Marcos Dantas", {}).get("classificacao") == "inadimplente", "vencido = inadimplente")
    checar(por.get("Paulo Vítor Souza Lima - Paulo Som", {}).get("classificacao") == "pago", "nome diferente no Asaas = pago")
    checar(por.get("Zeca Premios - Davi Alves Barros", {}).get("classificacao") == "pago", "cartão confirmado = pago")
    checar(por.get("[Luiz Augusto] Mateus Moura Viana [Mensalista]", {}).get("busca") == "sem_data", "sem cobrança na data")
    checar(por.get("Lucas show premiações", {}).get("classificacao") == "pago", "achado pelo quadro de nomes")
    checar(por.get("XyzPremios - Anderson Silva Gomes", {}).get("classificacao") == "nao_encontrado", "não encontrado")
    checar(len(por) == 6, f"6 vencidos conferidos (achou {len(por)}) — rolagem da lista funcionou")
    checar([p["nome"] for p in estado["porcentagem"]] == ["Campeões da Pista - Daniel Alves de Souza Filho"], "porcentagem")
    checar(estado["sem_data"] == ["Fulano Premios"], "tarefa sem data")
    link = por["Sortudo da Rifa - Marcos Dantas"]["cobrancas"][0]["link"]
    checar(link.endswith("/i/c1fatura"), "pegou o link da fatura: " + link)
    checar("inadimplente" in painel.inner_text("#chat"), "responde com o resumo na conversa")

    # ---------------- mensagens
    painel.click("#atalhos button[data-cmd=mensagens]")
    painel.wait_for_function("() => window.__painel.S.mensagens.length > 0")
    txt = painel.inner_text("#listaMensagens")
    checar("Olá, Marcos!" in txt and "/i/c1fatura" in txt and SF.br(SF.D(12)) in txt, "mensagem com nome, data e link")

    # ---------------- atualizar (desmarca 1, aplica os outros)
    painel.click("#abas button[data-aba=conversa]")
    painel.click("#atalhos button[data-cmd=atualizar]")
    painel.wait_for_selector("#listaAtualizar .cartao")
    checar(painel.locator("#listaAtualizar .cartao").count() == 4, "4 para atualizar (3 pagos + 1 porcentagem)")
    painel.locator("#listaAtualizar .cartao", has_text="Lucas show").locator("input").uncheck()
    painel.click("#aplicar")
    painel.wait_for_function("() => window.__painel.S.ocupado === true", timeout=10000)
    painel.wait_for_function("() => window.__painel.S.ocupado === false", timeout=180000)
    srv = estado_servidor()
    t = srv["tarefas"]
    from datetime import date
    def mais1(d):
        a, m = (d.year + (d.month == 12), d.month % 12 + 1)
        import calendar
        return date(a, m, min(d.day, calendar.monthrange(a, m)[1]))
    checar(t["a2"][2] == SF.br(mais1(SF.D(7))), f"Paulo: data +1 mês digitada de verdade ({t['a2'][2]})")
    checar(t["a3"][4] == "PAGO" and t["a3"][2] == SF.br(mais1(SF.D(38))), "Zeca: virou PAGO e data +1 mês")
    checar(t["a7"][2] == SF.br(mais1(SF.D(12))), "Campeões (porcentagem): data +1 mês")
    checar(t["a5"][2] == SF.br(SF.D(2)), "Lucas (desmarcado): não foi alterado")
    checar(t["a1"][2] == SF.br(SF.D(12)), "inadimplente não foi alterado")
    res = painel.inner_text("#listaAtualizar")
    checar(res.count("✓ feito") == 3, "3 marcados como feitos na tela")

    # ---------------- mensagem para cliente com 'sem juros'
    painel.click("#abas button[data-aba=conversa]")
    painel.fill("#cmd", "mensagem pro Marcos, venceu 20/11/2026, sem juros")
    painel.press("#cmd", "Enter")
    painel.wait_for_function("() => document.querySelectorAll('#chat .bolha .acoes button.primario').length > 0 && !window.__painel.S.ocupado",
                             timeout=60000)
    painel.locator("#chat .bolha .acoes button.primario").last.click()
    painel.wait_for_function("() => window.__painel.S.mensagens[0] && window.__painel.S.mensagens[0].texto.includes('sem cobrança de juros')",
                             timeout=60000)
    m = painel.evaluate("window.__painel.S.mensagens[0].texto")
    checar("20/11/2026" in m and SF.br(SF.D(12)) in m and "/i/c1fatura" in m, "mensagem sem juros com data original e nova")

    painel.screenshot(path=str(RAIZ / "testes-extensao" / "painel_teste.png"))
    reais = [e for e in erros if "Failed to load resource" not in e]
    checar(not reais, "sem erros no console do painel" + (": " + " | ".join(reais[:3]) if reais else ""))
    ctx.close()

print(f"\n{len(falhas)} FALHA(S)" if falhas else "\nExtensão testada de ponta a ponta: tudo certo.")
sys.exit(1 if falhas else 0)
