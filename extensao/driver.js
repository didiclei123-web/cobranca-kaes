/*
 * Quem clica e lê as telas do ClickUp e do Asaas, dentro do Edge, numa aba de trabalho.
 * - Leitura e cliques: scripts injetados na aba (chrome.scripting).
 * - Digitação da data no ClickUp: teclado "de verdade" via chrome.debugger
 *   (o Edge mostra uma faixa "começou a depurar este navegador" enquanto digita).
 */
(function (raiz) {
  "use strict";
  const R = raiz.Regras;
  const esperarMs = (ms) => new Promise((r) => setTimeout(r, ms));

  // ------------------------------------------------------------ funções que rodam DENTRO da página
  // (cada uma precisa ser independente: nada de variáveis de fora)

  function pgTarefasVisiveis() {
    return [...document.querySelectorAll('a[data-test="task-row-main__link"]')].map((a) => {
      const cel = a.closest("cu-task-name-cell");
      const m = cel ? cel.innerText.match(/Status atual:\s*([^\n]+)/) : null;
      return { nome: a.innerText.split("\n")[0].trim(), url: a.href, status: m ? m[1].trim().toLowerCase() : "" };
    });
  }

  function pgRolarLista() {
    const links = document.querySelectorAll('a[data-test="task-row-main__link"]');
    let el = links[links.length - 1];
    while (el && el !== document.body) {
      const st = getComputedStyle(el);
      if (el.scrollHeight > el.clientHeight + 20 && /(auto|scroll)/.test(st.overflowY)) {
        const antes = el.scrollTop;
        el.scrollBy(0, 600);
        return el.scrollTop !== antes;
      }
      el = el.parentElement;
    }
    window.scrollBy(0, 600);
    return false;
  }

  function pgTarefaCarregada() {
    return !!document.querySelector('[data-test="view-task__body"] [data-test="task-hero-section__dates"]');
  }

  function pgCampo(nome) {
    const painel = document.querySelector('[data-test="view-task__body"]');
    if (!painel) return "";
    const el = [...painel.querySelectorAll("[aria-label]")].find((e) =>
      e.getAttribute("aria-label").toLowerCase().includes(("campo personalizado " + nome).toLowerCase()));
    if (!el) return "";
    const rotulo = el.getAttribute("aria-label");
    if (rotulo.toLowerCase().startsWith("definir valor")) return "";
    return rotulo.includes(nome + ".") ? rotulo.split(nome + ".").pop().trim() : "";
  }

  function pgClicarVencimento() {
    const painel = document.querySelector('[data-test="view-task__body"]');
    const b = painel && painel.querySelector('[data-test="task-dates-display-button"]:has(use[href="#cu3-icon-dateDue"])');
    if (!b) return false;
    b.click();
    return true;
  }

  function pgLerCampoData(focar) {
    const i = document.querySelector('input[placeholder="Data de vencimento"]');
    if (!i) return null;
    if (focar) { i.focus(); i.select(); }
    return i.value;
  }

  function pgClicarCampoPagamento() {
    const painel = document.querySelector('[data-test="view-task__body"]');
    const el = painel && [...painel.querySelectorAll("[aria-label]")].find((e) =>
      e.getAttribute("aria-label").toLowerCase().includes("campo personalizado status do pagamento"));
    if (!el) return false;
    el.click();
    return true;
  }

  function pgClicarOpcao(valor) {
    const o = document.querySelector(`[data-test="custom-fields__select-menu_dropdown-item-${valor}"]`);
    if (!o) return false;
    o.click();
    return true;
  }

  function pgLinhasAsaas() {
    function* walk(root) { for (const e of root.querySelectorAll("*")) { yield e; if (e.shadowRoot) yield* walk(e.shadowRoot); } }
    const rows = [...walk(document)].filter((e) => e.tagName === "ATLAS-TABLE-ROW");
    const linhas = rows.map((r, i) => ({
      indice: i,
      cols: [...r.querySelectorAll("atlas-table-col")].map((c) => c.innerText.trim().replace(/\s+/g, " ")),
      icones: [...r.querySelectorAll("atlas-icon")].map((x) => x.getAttribute("name") || ""),
    })).filter((x) => x.cols.length >= 5 && /\d{2}\/\d{2}\/\d{4}/.test(x.cols.join(" ")));
    const todos = [...walk(document)];
    const vazio = todos.some((e) => e.tagName === "ATLAS-EMPTY-STATE") ||
      /Nenhuma cobrança/i.test(document.body.innerText) ||
      todos.some((e) => e.shadowRoot && /Nenhuma cobrança/i.test(e.shadowRoot.textContent));
    return { linhas, vazio };
  }

  function pgClicarLinhaAsaas(indice) {
    function* walk(root) { for (const e of root.querySelectorAll("*")) { yield e; if (e.shadowRoot) yield* walk(e.shadowRoot); } }
    const rows = [...walk(document)].filter((e) => e.tagName === "ATLAS-TABLE-ROW");
    if (!rows[indice]) return false;
    const cols = [...rows[indice].querySelectorAll("atlas-table-col")];
    (cols.find((c) => /\d{2}\/\d{2}\/\d{4}/.test(c.innerText)) || cols[0]).click();
    return true;
  }

  function pgDetalheAsaas() {
    const t = document.body.innerText;
    const sit = (t.match(/Situação\s*\n+\s*([^\n]+)/) || [])[1] || "";
    const cli = (t.match(/Cliente\s*\n+\s*([^\n]+)/) || [])[1] || "";
    const a = [...document.querySelectorAll("a")].find((x) => /Visualizar fatura/i.test(x.innerText));
    return { situacao: sit.trim(), cliente: cli.trim(), link: a ? a.href : "" };
  }

  function pgPareceLogin() {
    return /login|signin|entrar/i.test(location.pathname) ||
      !!document.querySelector('input[type="password"]');
  }

  // ------------------------------------------------------------ o driver
  class DriverEdge {
    constructor(cfg, { avisar = () => {}, pedirLogin = async () => {}, cancelado = () => false } = {}) {
      this.cfg = cfg;
      this.avisar = avisar;
      this.pedirLogin = pedirLogin;
      this.cancelado = cancelado;
      this.tabId = null;
      this.base = (cfg.asaas_base || "https://www.asaas.com").replace(/\/$/, "");
    }

    checar() { if (this.cancelado()) throw new raiz.Motor.Cancelado(); }

    async aba(urlInicial) {
      if (this.tabId !== null) {
        try { await chrome.tabs.get(this.tabId); return this.tabId; } catch (e) { this.tabId = null; }
      }
      const t = await chrome.tabs.create({ url: urlInicial || "about:blank", active: true });
      this.tabId = t.id;
      return this.tabId;
    }

    async urlAtual() {
      try { return (await chrome.tabs.get(this.tabId)).url || ""; } catch (e) { return ""; }
    }

    async ir(url) {
      this.checar();
      const nova = this.tabId === null;
      const id = await this.aba(url);
      for (let tentativa = 0; tentativa < 3; tentativa++) {
        if (!nova || tentativa > 0) await chrome.tabs.update(id, { url, active: true });
        await esperarMs(500);
        let t;
        for (let i = 0; i < 100; i++) {
          t = await chrome.tabs.get(id);
          const chegou = (t.url || t.pendingUrl || "") !== "" && !(t.url || "").startsWith("about:");
          if (t.status === "complete" && chegou) break;
          await esperarMs(300);
        }
        if (t && t.url && !t.url.startsWith("about:")) break;  // carregou; senão tenta de novo
        this.avisar("A aba não carregou, tentando de novo...");
      }
      await esperarMs(800);
    }

    async exec(func, args = []) {
      for (let tentativa = 0; tentativa < 3; tentativa++) {
        try {
          const [r] = await chrome.scripting.executeScript({ target: { tabId: await this.aba() }, func, args });
          return r ? r.result : undefined;
        } catch (e) {
          if (tentativa === 2) throw e;
          await esperarMs(700);
        }
      }
    }

    async esperar(func, args = [], segundos = 30) {
      const fim = Date.now() + segundos * 1000;
      while (Date.now() < fim) {
        this.checar();
        let v;
        try { v = await this.exec(func, args); } catch (e) { v = null; }
        if (v) return v;
        await esperarMs(500);
      }
      return null;
    }

    // ---------------------------------------------------- teclado de verdade (depurador)
    async teclado(acoes) {
      const alvo = { tabId: await this.aba() };
      await chrome.debugger.attach(alvo, "1.3");
      try {
        for (const a of acoes) {
          if (a.texto) {
            await chrome.debugger.sendCommand(alvo, "Input.insertText", { text: a.texto });
          } else if (a.tecla) {
            const cod = { Enter: 13, Escape: 27 }[a.tecla];
            const base = { key: a.tecla, code: a.tecla, windowsVirtualKeyCode: cod, nativeVirtualKeyCode: cod };
            await chrome.debugger.sendCommand(alvo, "Input.dispatchKeyEvent", { type: "rawKeyDown", ...base,
              ...(a.tecla === "Enter" ? { text: "\r", unmodifiedText: "\r" } : {}) });
            if (a.tecla === "Enter") await chrome.debugger.sendCommand(alvo, "Input.dispatchKeyEvent", { type: "char", ...base, text: "\r" });
            await chrome.debugger.sendCommand(alvo, "Input.dispatchKeyEvent", { type: "keyUp", ...base });
          }
          await esperarMs(a.esperar || 250);
        }
      } finally {
        try { await chrome.debugger.detach(alvo); } catch (e) { /* já saiu */ }
      }
    }

    // ---------------------------------------------------- login
    async loginClickup() {
      await this.ir(this.cfg.clickup_url_lista);
      if (await this.esperar(() => document.querySelectorAll('a[data-test="task-row-main__link"]').length > 0, [], 25)) return;
      await this.pedirLogin("ClickUp");
      await this.ir(this.cfg.clickup_url_lista);
      if (!(await this.esperar(() => document.querySelectorAll('a[data-test="task-row-main__link"]').length > 0, [], 40))) {
        throw new Error("Não consegui abrir a lista do ClickUp. Confira o link nas Configurações e se você está logado.");
      }
    }

    async loginAsaas() {
      await this.ir(this.base + "/payment/list");
      await esperarMs(2500);
      const url = await this.urlAtual();
      if (url.includes("/payment") && !(await this.exec(pgPareceLogin))) return;
      await this.pedirLogin("Asaas");
      await this.ir(this.base + "/payment/list");
    }

    // ---------------------------------------------------- ClickUp
    async listarTarefasClickup(statusAlvo) {
      if (!(await this.urlAtual()).startsWith(this.cfg.clickup_url_lista)) await this.loginClickup();
      await esperarMs(1500);
      const achadas = new Map();
      let parado = 0;
      for (let i = 0; i < 150 && parado < 5; i++) {
        this.checar();
        const antes = achadas.size;
        for (const t of (await this.exec(pgTarefasVisiveis)) || []) if (!achadas.has(t.url)) achadas.set(t.url, t);
        parado = achadas.size === antes ? parado + 1 : 0;
        await this.exec(pgRolarLista);
        await esperarMs(500);
      }
      const alvo = new Set(statusAlvo.map(R.semAcento));
      const tarefas = [...achadas.values()].filter((t) => alvo.has(R.semAcento(t.status)));
      for (const s of statusAlvo) {
        if (!tarefas.some((t) => R.semAcento(t.status) === R.semAcento(s))) {
          this.avisar(`! Nenhuma tarefa no status "${s}" (o grupo está recolhido ou vazio?)`);
        }
      }
      return tarefas;
    }

    async abrirTarefa(url) {
      await this.ir(url);
      if (!(await this.esperar(pgTarefaCarregada, [], 40))) throw new Error("a tarefa não carregou");
      await esperarMs(1200);
    }

    async lerVencimentoAberto() {
      if (!(await this.exec(pgClicarVencimento))) return { botao: false, valor: null };
      const v = await this.esperar(pgLerCampoData, [false], 8);
      return { botao: true, valor: v };
    }

    async lerTarefa(url) {
      await this.abrirTarefa(url);
      const porcentagem = await this.exec(pgCampo, ["Porcentagem"]);
      const status_pagamento = await this.exec(pgCampo, ["Status do Pagamento"]);
      const { valor } = await this.lerVencimentoAberto();
      return { vencimento: R.lerData(valor), porcentagem: porcentagem || "", status_pagamento: status_pagamento || "" };
    }

    async alterarTarefa(url, novaIso, marcarPago) {
      await this.abrirTarefa(url);
      const problemas = [];
      if (novaIso) {
        if (!(await this.exec(pgClicarVencimento))) {
          problemas.push("não achei o botão da data de vencimento");
        } else if ((await this.esperar(pgLerCampoData, [true], 8)) === null) {
          problemas.push("o campo da data não abriu");
        } else {
          await this.exec(pgLerCampoData, [true]);
          await this.teclado([{ texto: R.dataBr(novaIso, true), esperar: 400 }, { tecla: "Enter", esperar: 1500 },
                              { tecla: "Escape", esperar: 800 }]);
          const { valor } = await this.lerVencimentoAberto();
          await this.teclado([{ tecla: "Escape", esperar: 500 }]);
          if (R.lerData(valor) !== novaIso) problemas.push(`a data ficou ${valor || "?"} em vez de ${R.dataBr(novaIso)}`);
        }
      }
      if (marcarPago && (await this.exec(pgCampo, ["Status do Pagamento"])).toUpperCase() !== "PAGO") {
        if (!(await this.exec(pgClicarCampoPagamento))) {
          problemas.push("não achei o campo Status do Pagamento");
        } else if (!(await this.esperar(pgClicarOpcao, ["PAGO"], 8))) {
          problemas.push("não achei a opção PAGO");
        } else {
          await esperarMs(1500);
          if ((await this.exec(pgCampo, ["Status do Pagamento"])).toUpperCase() !== "PAGO") {
            problemas.push("Status do Pagamento não ficou PAGO");
          }
        }
      }
      return problemas;
    }

    // ---------------------------------------------------- Asaas
    async carregarBusca(url) {
      await this.ir(url);
      for (let i = 0; i < 24; i++) {
        this.checar();
        const r = await this.exec(pgLinhasAsaas);
        if (r && (r.linhas.length || r.vazio)) return r.linhas;
        await esperarMs(500);
      }
      return [];
    }

    async buscarCobrancas(termo) {
      const url = `${this.base}/payment/list?customerAccountText=${encodeURIComponent(termo)}&itemsPerPage=50`;
      const linhas = await this.carregarBusca(url);
      return linhas.map((l) => {
        const datas = l.cols.map(R.lerData).filter(Boolean);
        return { indice: l.indice, cliente: l.cols[0], valor: l.cols[1], descricao: l.cols[2],
                 vencimento: datas[datas.length - 1] || null, icones: l.icones, termo, url_busca: url };
      });
    }

    async detalharCobranca(linha) {
      if ((await this.urlAtual()) !== linha.url_busca) await this.carregarBusca(linha.url_busca);
      await this.exec(pgClicarLinhaAsaas, [linha.indice]);
      for (let i = 0; i < 40; i++) {
        if ((await this.urlAtual()).includes("/payment/show/")) break;
        await esperarMs(500);
      }
      if (!(await this.urlAtual()).includes("/payment/show/")) return { situacao: "?", cliente: linha.cliente, link: "" };
      await esperarMs(1500);
      const d = (await this.esperar(() => /Situação/.test(document.body.innerText), [], 10)) && (await this.exec(pgDetalheAsaas));
      return { ...(d || { situacao: "?", cliente: linha.cliente, link: "" }), url_cobranca: await this.urlAtual() };
    }

    async fechar() {
      if (this.tabId !== null) { try { await chrome.tabs.remove(this.tabId); } catch (e) { /* já fechada */ } }
      this.tabId = null;
    }
  }

  raiz.DriverEdge = DriverEdge;
})(typeof self !== "undefined" ? self : globalThis);
