"""
Tudo que é clique e leitura de tela no ClickUp e no Asaas (sem API).
Usa um navegador próprio do programa, com login salvo na pasta 'perfil_navegador'.
"""
import time
from urllib.parse import quote

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from base import PASTA_PERFIL
from regras import ler_data, data_br, sem_acento

# JavaScript que lê as linhas da tabela do Asaas (os componentes ficam em "shadow DOM")
JS_LINHAS_ASAAS = r"""
() => {
  function* walk(root){ for (const e of root.querySelectorAll('*')) { yield e; if (e.shadowRoot) yield* walk(e.shadowRoot); } }
  const rows = [...walk(document)].filter(e => e.tagName === 'ATLAS-TABLE-ROW');
  return rows.map((r, i) => {
    const cols = [...r.querySelectorAll('atlas-table-col')].map(c => c.innerText.trim().replace(/\s+/g, ' '));
    const icones = [...r.querySelectorAll('atlas-icon')].map(x => x.getAttribute('name') || '');
    return { indice: i, cols, icones };
  }).filter(x => x.cols.length >= 5 && /\d{2}\/\d{2}\/\d{4}/.test(x.cols.join(' ')));
}
"""

JS_CLICAR_LINHA_ASAAS = r"""
(indice) => {
  function* walk(root){ for (const e of root.querySelectorAll('*')) { yield e; if (e.shadowRoot) yield* walk(e.shadowRoot); } }
  const rows = [...walk(document)].filter(e => e.tagName === 'ATLAS-TABLE-ROW');
  const cols = [...rows[indice].querySelectorAll('atlas-table-col')];
  const alvo = cols.find(c => /\d{2}\/\d{2}\/\d{4}/.test(c.innerText)) || cols[0];
  alvo.click();
}
"""

JS_TAREFAS_VISIVEIS = r"""
() => [...document.querySelectorAll('a[data-test="task-row-main__link"]')].map(a => {
  const cel = a.closest('cu-task-name-cell');
  const m = cel ? cel.innerText.match(/Status atual:\s*([^\n]+)/) : null;
  return { nome: a.innerText.split('\n')[0].trim(), url: a.href, status: m ? m[1].trim().toLowerCase() : '' };
})
"""


class Navegador:
    def __init__(self, cfg: dict, avisar=print, pedir_login=None, perfil=None, headless=False):
        """
        avisar(texto): mostra mensagens de andamento.
        pedir_login(site): mostra um aviso e só retorna quando a pessoa disser que já entrou.
        Usa o Microsoft Edge que já vem no Windows (nada é baixado).
        """
        self.cfg = cfg
        self.avisar = avisar
        self.pedir_login = pedir_login or (lambda site: input(f"Faça login no {site} e aperte ENTER... "))
        self._pw = sync_playwright().start()
        opcoes = dict(user_data_dir=str(perfil or PASTA_PERFIL), headless=headless,
                      viewport={"width": 1400, "height": 850}, locale="pt-BR")
        self.ctx, erros = None, []
        for canal in (cfg.get("navegador") or "msedge", "msedge", "chrome"):
            try:
                self.ctx = self._pw.chromium.launch_persistent_context(channel=canal, **opcoes)
                self.canal = canal
                break
            except Exception as e:
                erros.append(f"{canal}: {e}")
        if self.ctx is None:
            self._pw.stop()
            raise RuntimeError("Não consegui abrir o Edge nem o Chrome.\n" + "\n".join(erros))
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        self.page.set_default_timeout(20000)

    def fechar(self):
        try:
            self.ctx.close()
        finally:
            self._pw.stop()

    # ------------------------------------------------------------ login
    def _garantir_login(self, site: str, url_teste: str, sinal_logado):
        self.page.goto(url_teste)
        time.sleep(4)
        if sinal_logado():
            return
        self.avisar(f"Aguardando login no {site}...")
        self.pedir_login(site)
        self.page.goto(url_teste)
        time.sleep(4)

    def login_clickup(self):
        self._garantir_login("ClickUp", self.cfg["clickup_url_lista"],
                             lambda: "login" not in self.page.url and
                             self.page.locator('a[data-test="task-row-main__link"]').count() > 0)

    def login_asaas(self):
        self._garantir_login("Asaas", "https://www.asaas.com/payment/list",
                             lambda: "login" not in self.page.url and "/payment" in self.page.url)

    # ------------------------------------------------------------ ClickUp: lista
    def listar_tarefas_clickup(self, status_alvo: list) -> list:
        """Rola a lista e coleta nome, link e status de todas as tarefas visíveis."""
        p = self.page
        p.goto(self.cfg["clickup_url_lista"])
        p.wait_for_selector('a[data-test="task-row-main__link"]', timeout=40000)
        time.sleep(2)
        encontrados, parado = {}, 0
        p.mouse.move(800, 450)
        for _ in range(120):
            antes = len(encontrados)
            for t in p.evaluate(JS_TAREFAS_VISIVEIS):
                encontrados.setdefault(t["url"], t)
            parado = parado + 1 if len(encontrados) == antes else 0
            if parado >= 5:
                break
            p.mouse.wheel(0, 500)
            time.sleep(0.6)
        alvo = {sem_acento(s) for s in status_alvo}
        tarefas = [t for t in encontrados.values() if sem_acento(t["status"]) in alvo]
        for s in status_alvo:
            if not any(sem_acento(t["status"]) == sem_acento(s) for t in tarefas):
                self.avisar(f"  ! Nenhuma tarefa encontrada no status '{s}' "
                            f"(o grupo está recolhido ou vazio?)")
        return tarefas

    # ------------------------------------------------------------ ClickUp: tarefa
    def _abrir_tarefa(self, url: str):
        self.page.goto(url)
        self.page.wait_for_selector('[data-test="view-task__body"] [data-test="task-hero-section__dates"]',
                                    timeout=40000)
        time.sleep(1.5)

    def _painel(self):
        """Só o painel da tarefa aberta (a lista continua carregada por trás)."""
        return self.page.locator('[data-test="view-task__body"]').first

    def _botao_vencimento(self):
        return self._painel().locator('[data-test="task-dates-display-button"]:has(use[href="#cu3-icon-dateDue"])').first

    def _campo(self, nome: str) -> str:
        loc = self._painel().locator(f'[aria-label*="campo personalizado {nome}" i]').first
        if loc.count() == 0:
            return ""
        rotulo = loc.get_attribute("aria-label") or ""
        if rotulo.lower().startswith("definir valor"):
            return ""
        return rotulo.split(f"{nome}.", 1)[-1].strip() if f"{nome}." in rotulo else ""

    def ler_tarefa(self, url: str) -> dict:
        """Lê vencimento (data exata), Porcentagem e Status do Pagamento."""
        self._abrir_tarefa(url)
        p = self.page
        venc = None
        botao = self._botao_vencimento()
        if botao.count():
            botao.click()
            campo = p.locator('input[placeholder="Data de vencimento"]').first
            campo.wait_for(timeout=8000)
            venc = ler_data(campo.input_value())
            p.keyboard.press("Escape")
            time.sleep(0.5)
        return {
            "vencimento": venc,
            "porcentagem": self._campo("Porcentagem"),
            "status_pagamento": self._campo("Status do Pagamento"),
        }

    def alterar_tarefa(self, url: str, nova_data=None, marcar_pago=False) -> list:
        """Faz as alterações e confere. Retorna lista de problemas (vazia = deu certo)."""
        self._abrir_tarefa(url)
        p, problemas = self.page, []
        if nova_data:
            botao = self._botao_vencimento()
            if not botao.count():
                problemas.append("não achei o botão da data de vencimento")
            else:
                botao.click()
                campo = p.locator('input[placeholder="Data de vencimento"]').first
                campo.wait_for(timeout=8000)
                campo.click()
                p.keyboard.press("Control+A")
                p.keyboard.type(data_br(nova_data, ano_curto=True), delay=60)
                p.keyboard.press("Enter")
                time.sleep(1.2)
                p.keyboard.press("Escape")
                time.sleep(1)
                # confere
                self._botao_vencimento().click()
                valor = ler_data(p.locator('input[placeholder="Data de vencimento"]').first.input_value())
                p.keyboard.press("Escape")
                if valor != nova_data:
                    problemas.append(f"data ficou {valor} em vez de {data_br(nova_data)}")
        if marcar_pago and self._campo("Status do Pagamento").upper() != "PAGO":
            self._painel().locator('[aria-label*="campo personalizado Status do Pagamento" i]').first.click()
            opcao = p.locator('[data-test="custom-fields__select-menu_dropdown-item-PAGO"]').first
            opcao.wait_for(timeout=8000)
            opcao.click()
            time.sleep(1.2)
            if self._campo("Status do Pagamento").upper() != "PAGO":
                problemas.append("Status do Pagamento não ficou PAGO")
        return problemas

    # ------------------------------------------------------------ Asaas
    def buscar_cobrancas(self, termo: str) -> list:
        """Pesquisa cobranças pelo nome do cliente. Retorna linhas da tabela."""
        p = self.page
        p.goto(f"https://www.asaas.com/payment/list?customerAccountText={quote(termo)}&itemsPerPage=50")
        linhas = []
        for _ in range(12):  # espera a tabela carregar
            time.sleep(1)
            linhas = p.evaluate(JS_LINHAS_ASAAS)
            if linhas or "Nenhuma cobrança" in p.inner_text("body"):
                break
        saida = []
        for l in linhas:
            cols = l["cols"]
            venc = next((ler_data(c) for c in reversed(cols) if ler_data(c)), None)
            saida.append({"indice": l["indice"], "cliente": cols[0], "valor": cols[1],
                          "descricao": cols[2], "vencimento": venc, "icones": l["icones"],
                          "termo": termo, "url_busca": p.url})
        return saida

    def detalhar_cobranca(self, linha: dict) -> dict:
        """Abre a cobrança e lê Situação, Cliente e o link de 'Visualizar fatura'."""
        p = self.page
        if p.url != linha["url_busca"]:
            p.goto(linha["url_busca"])
            for _ in range(12):
                time.sleep(1)
                if p.evaluate(JS_LINHAS_ASAAS):
                    break
        p.evaluate(JS_CLICAR_LINHA_ASAAS, linha["indice"])
        try:
            p.wait_for_url("**/payment/show/**", timeout=20000)
        except PWTimeout:
            return {"situacao": "?", "link": "", "cliente": linha["cliente"]}
        time.sleep(2.5)
        dados = p.evaluate(r"""() => {
            const t = document.body.innerText;
            const sit = (t.match(/Situação\s*\n+\s*([^\n]+)/) || [])[1] || '?';
            const cli = (t.match(/Cliente\s*\n+\s*([^\n]+)/) || [])[1] || '';
            const a = [...document.querySelectorAll('a')].find(a => /Visualizar fatura/i.test(a.innerText));
            return { situacao: sit.trim(), cliente: cli.trim(), link: a ? a.href : '' };
        }""")
        dados["url_cobranca"] = p.url
        return dados
