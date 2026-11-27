/* Painel lateral: conversa, botões, resultados, mensagens, atualização e configurações. */
(function () {
  "use strict";
  const R = self.Regras, M = self.Motor;
  const $ = (s) => document.querySelector(s);
  const el = (tag, props = {}, ...filhos) => {
    const e = Object.assign(document.createElement(tag), props);
    for (const f of filhos) e.append(f);
    return e;
  };

  // ------------------------------------------------------------ armazenamento
  const Arm = {
    async ler(k, padrao) { const r = await chrome.storage.local.get(k); return r[k] === undefined ? padrao : r[k]; },
    async gravar(k, v) { await chrome.storage.local.set({ [k]: v }); },
    async config() { return { ...self.CONFIG_PADRAO, ...(await this.ler("config", {})) }; },
    async mapa() { return await this.ler("mapa", {}); },
    async salvarEstado(e) { await this.gravar("estado", e); },
    async estado() { return await this.ler("estado", null); },
  };

  // ------------------------------------------------------------ estado da tela
  const S = { ocupado: false, cancelar: false, estado: null, mensagens: [], plano: [], filtro: "todos", ia: null };

  const ROTULOS = {
    inadimplente: "🔴 Inadimplente", pago: "🟢 Pago", aguardando: "🟡 Aguardando", outro: "🟡 Outro",
    nao_encontrado: "⚠️ Não encontrado", porcentagem: "📊 Porcentagem",
  };

  // ------------------------------------------------------------ conversa
  function bolha(tipo, conteudo) {
    const b = el("div", { className: "bolha " + tipo });
    if (typeof conteudo === "string") b.textContent = conteudo; else b.append(conteudo);
    $("#chat").append(b);
    $("#chat").scrollTop = $("#chat").scrollHeight;
    return b;
  }
  const diz = (t) => bolha("ela", t);
  const registro = (t) => { bolha("log", new Date().toISOString().slice(14, 19) + " " + t); status(t); };

  function status(t) { $("#status").textContent = t; }
  function progresso(a, t, texto) {
    $("#barraCheia").style.width = Math.round((100 * a) / Math.max(t, 1)) + "%";
    status(texto);
  }

  function irPara(aba) {
    document.querySelectorAll("#abas button").forEach((b) => b.classList.toggle("ativa", b.dataset.aba === aba));
    document.querySelectorAll(".aba").forEach((s) => s.classList.toggle("ativa", s.id === "aba-" + aba));
  }

  function ocupar(sim) {
    S.ocupado = sim;
    S.cancelar = false;
    $("#parar").hidden = !sim;
    document.querySelectorAll("#atalhos button, #aplicar").forEach((b) => { b.disabled = sim; });
    if (!sim) { $("#barraCheia").style.width = "0"; status("Pronto."); }
  }

  function pedirLogin(site) {
    return new Promise((resolve) => {
      const conteudo = el("div", {}, `Preciso que você entre no ${site} na aba que eu abri. Depois clique aqui:`);
      const bt = el("button", { className: "primario", textContent: "Já entrei, pode seguir" });
      bt.onclick = () => { bt.disabled = true; resolve(); };
      conteudo.append(el("div", { className: "acoes" }, bt));
      bolha("ela", conteudo);
      irPara("conversa");
    });
  }

  async function novoDriver() {
    return new self.DriverEdge(await Arm.config(), {
      avisar: registro, pedirLogin, cancelado: () => S.cancelar,
    });
  }

  async function trabalhar(titulo, funcao) {
    if (S.ocupado) { diz("Ainda estou terminando o pedido anterior. Se quiser, clique em Parar."); return; }
    const cfg = await Arm.config();
    if (!cfg.clickup_url_lista) {
      diz("Antes, cole o link da sua lista do ClickUp (aba “Visão Geral”) nas Configurações ⚙️ e salve.");
      irPara("config");
      return;
    }
    ocupar(true);
    status(titulo);
    const driver = await novoDriver();
    try {
      await funcao(driver);
    } catch (e) {
      if (e instanceof M.Cancelado) diz("Parei. Nada além do que já estava feito foi alterado.");
      else { diz("Deu um erro: " + e.message + "\n\nSe o ClickUp ou o Asaas mudaram de visual, me avise para ajustar."); console.error(e); }
    } finally {
      ocupar(false);
    }
  }

  // ------------------------------------------------------------ comandos
  async function cmdConferir() {
    await trabalhar("Conferindo...", async (driver) => {
      diz("Combinado! Vou abrir o ClickUp, ver quem venceu e conferir cada um no Asaas. Pode acompanhar na aba que vou abrir.");
      const estado = await M.conferir(driver, Arm, { avisar: registro, progresso, cancelado: () => S.cancelar });
      S.estado = estado;
      renderResultados();
      const cont = contagem(estado);
      diz(`Pronto! ${cont.inadimplente || 0} inadimplente(s), ${cont.pago || 0} pago(s), ` +
          `${cont.nao_encontrado || 0} não encontrado(s) no Asaas e ${cont.porcentagem || 0} de porcentagem.\n` +
          `Veja tudo na aba Resultados. Quer que eu gere as mensagens de cobrança?`);
      const acoes = el("div", { className: "acoes" },
        el("button", { className: "secundario", textContent: "✉️ Gerar mensagens", onclick: cmdMensagens }),
        el("button", { className: "secundario", textContent: "📋 Ver resultados", onclick: () => irPara("resultados") }));
      bolha("ela", acoes);
    });
  }

  function estadoOk() {
    if (!S.estado) { diz("Primeiro preciso conferir os vencidos. Clique em 🔎 Conferir vencidos."); return false; }
    if (S.estado.data !== R.hoje()) diz(`Atenção: a última conferência é de ${R.dataBr(S.estado.data)}. Vou usar ela mesmo assim.`);
    return true;
  }

  async function cmdMensagens() {
    if (!estadoOk()) return;
    S.mensagens = await M.mensagensInadimplentes(S.estado, Arm);
    renderMensagens();
    if (!S.mensagens.length) { diz("Nenhum inadimplente na última conferência. 🎉"); return; }
    diz(`Gerei ${S.mensagens.length} mensagem(ns). Estão na aba Mensagens, com botão de copiar.`);
    irPara("mensagens");
  }

  function cmdAtualizar() {
    if (!estadoOk()) return;
    S.plano = M.planoAtualizacao(S.estado);
    renderAtualizar();
    if (!S.plano.length) { diz("Nada para atualizar (ou já foi atualizado)."); return; }
    diz(`Separei ${S.plano.length} cliente(s) para marcar como PAGO e empurrar o vencimento. ` +
        "Confira na aba Atualizar, desmarque quem não quiser e clique em Aplicar.");
    irPara("atualizar");
  }

  async function aplicarMarcados() {
    const marcados = S.plano.filter((it) => it._marcado && !it._feito);
    if (!marcados.length) { status("Nenhum marcado."); return; }
    if (!confirm(`Alterar ${marcados.length} tarefa(s) no ClickUp?\n\nStatus do Pagamento = PAGO e vencimento +1 mês.`)) return;
    await trabalhar("Atualizando ClickUp...", async (driver) => {
      let n = 0;
      await M.aplicar(driver, Arm, S.estado, marcados, {
        cancelado: () => S.cancelar,
        aoTerminarItem: (it, problemas) => {
          n++;
          progresso(n, marcados.length, "Atualizado: " + it.nome);
          it._feito = !problemas.length;
          it._resultado = problemas.length ? "✗ " + problemas.join("; ") : "✓ feito";
          registro(`${it.nome}: ${problemas.length ? problemas.join("; ") : "ok"}`);
          renderAtualizar();
        },
      });
      const ok = marcados.filter((m) => m._feito).length;
      diz(`Atualizei ${ok} de ${marcados.length} no ClickUp.` + (ok < marcados.length ? " Veja os que falharam na aba Atualizar." : " ✅"));
    });
  }

  function cmdMensagemCliente(cliente = "", dataOriginal = "", semJuros = false) {
    const form = el("form");
    const iCli = el("input", { placeholder: "Nome do cliente", value: cliente || "" });
    const cSj = el("input", { type: "checkbox", checked: !!semJuros });
    const iData = el("input", { placeholder: "Data original (dd/mm/aaaa)", value: dataOriginal || "" });
    const bt = el("button", { className: "primario", type: "submit", textContent: "Buscar no Asaas" });
    form.append(el("div", {}, "Para qual cliente?"), iCli,
      el("label", { style: "flex-direction:row;font-weight:400;align-items:center;gap:6px" }, cSj, "Vencimento alterado sem juros"),
      iData, bt);
    form.onsubmit = async (ev) => {
      ev.preventDefault();
      const nome = iCli.value.trim();
      if (!nome) return;
      const dOrig = R.lerData(iData.value);
      if (cSj.checked && !dOrig) { iData.focus(); status("Informe a data original."); return; }
      bt.disabled = true;
      bolha("eu", `Mensagem para ${nome}` + (cSj.checked ? `, venceu ${R.dataBr(dOrig)}, sem juros` : ""));
      await buscarParaCliente(nome, cSj.checked ? R.dataBr(dOrig) : null, cSj.checked);
    };
    bolha("ela", form);
    if (!cliente) iCli.focus(); else if (semJuros && !dataOriginal) iData.focus(); else if (cliente && (!semJuros || dataOriginal)) form.requestSubmit();
  }

  async function buscarParaCliente(nome, dataOriginal, semJuros) {
    await trabalhar("Buscando cobranças...", async (driver) => {
      const linhas = await M.buscarCobrancasCliente(driver, Arm, nome);
      if (!linhas.length) { diz(`Não encontrei cobranças para “${nome}” no Asaas. Tente outro pedaço do nome.`); return; }
      const caixa = el("div", {}, "Qual cobrança? (a mais recente vencida está destacada)");
      const acoes = el("div", { className: "acoes", style: "flex-direction:column" });
      const primeiraVencida = linhas.findIndex((l) => l.dica === "vencida");
      linhas.slice(0, 15).forEach((l, i) => {
        const b = el("button", { className: i === primeiraVencida ? "primario" : "secundario",
          textContent: `${R.dataBr(l.vencimento) || "?"} · ${l.valor} · ${l.dica}\n${l.cliente}` });
        b.style.whiteSpace = "pre-wrap";
        b.onclick = () => { acoes.querySelectorAll("button").forEach((x) => { x.disabled = true; }); gerarDaCobranca(nome, l, dataOriginal, semJuros); };
        acoes.append(b);
      });
      caixa.append(acoes);
      bolha("ela", caixa);
    });
  }

  async function gerarDaCobranca(nome, linha, dataOriginal, semJuros) {
    await trabalhar("Abrindo a cobrança...", async (driver) => {
      const { situacao, texto } = await M.mensagemDaCobranca(driver, Arm, nome, linha, dataOriginal, semJuros);
      S.mensagens = [{ nome: `${nome} — ${R.dataBr(linha.vencimento)}`, texto }, ...S.mensagens];
      renderMensagens();
      const caixa = el("div", {}, `Situação no Asaas: ${situacao}. Aqui está a mensagem:\n\n`, el("div", { className: "msg", textContent: texto }));
      caixa.append(el("div", { className: "acoes" }, botaoCopiar(texto)));
      bolha("ela", caixa);
      await driver.fechar();
    });
  }

  function ajuda() {
    diz("Posso:\n• 🔎 Conferir quem venceu no ClickUp e se pagou no Asaas\n• ✉️ Gerar as mensagens de cobrança dos inadimplentes\n" +
        "• ✅ Marcar os pagos como PAGO e empurrar o vencimento no ClickUp\n• 👤 Fazer a mensagem de um cliente específico\n\n" +
        "Pode pedir do seu jeito, ex.: “quem tá devendo?”, “gera as mensagens”, “mensagem pro Marcos, venceu 20/11/2026, sem juros”.");
  }

  // ------------------------------------------------------------ entender pedidos
  async function prepararIA() {
    try {
      if (typeof LanguageModel !== "undefined" && (await LanguageModel.availability()) === "available") {
        S.ia = await LanguageModel.create({
          initialPrompts: [{ role: "system", content:
            'Converta pedidos em português para JSON {"acao","cliente","data_original","sem_juros"}. ' +
            "acao: conferir | mensagens | atualizar | mensagem_cliente | ajuda | parar. " +
            "data_original no formato dd/mm/aaaa ou null. Responda só o JSON." }],
        });
      }
    } catch (e) { S.ia = null; }
    $("#modoIA").textContent = S.ia ? "Entendendo pedidos com a IA do Edge ✓" : "Entendendo pedidos por palavras-chave";
  }

  async function interpretar(texto) {
    const base = R.interpretarPalavrasChave(texto);
    if (!S.ia || base.acao === "parar") return base;
    try {
      const resp = await S.ia.prompt(texto);
      const j = JSON.parse(resp.slice(resp.indexOf("{"), resp.lastIndexOf("}") + 1));
      return R.ACOES.includes(j.acao) ? { ...base, ...j, sem_juros: !!j.sem_juros } : base;
    } catch (e) { return base; }
  }

  async function executar(cmd, textoOriginal) {
    switch (cmd.acao) {
      case "conferir": return cmdConferir();
      case "mensagens": return cmdMensagens();
      case "atualizar": return cmdAtualizar();
      case "mensagem_cliente": return cmdMensagemCliente(cmd.cliente || "", cmd.data_original || "", cmd.sem_juros);
      case "ajuda": return ajuda();
      case "parar": if (S.ocupado) { S.cancelar = true; diz("Ok, vou parar no próximo passo."); } else diz("Não estou fazendo nada agora."); return;
      default: diz(`Não entendi “${textoOriginal}”. Use os botões abaixo ou tente de outro jeito (ex.: “quem tá devendo?”).`);
    }
  }

  // ------------------------------------------------------------ telas
  function contagem(estado) {
    const c = {};
    for (const r of estado.resultados) { const k = ROTULOS[r.classificacao] ? r.classificacao : "outro"; c[k] = (c[k] || 0) + 1; }
    c.porcentagem = estado.porcentagem.length;
    return c;
  }

  function link(url, texto) { return el("a", { href: url, target: "_blank", textContent: texto }); }

  function renderResultados() {
    const e = S.estado, lista = $("#listaResultados");
    lista.replaceChildren();
    $("#filtros").replaceChildren();
    if (!e) return;
    const cont = contagem(e);
    $("#resumo").textContent = `Conferência de ${R.dataBr(e.data)}` + (e.sem_data.length ? ` · sem data: ${e.sem_data.join(", ")}` : "");
    for (const k of ["todos", ...Object.keys(ROTULOS)]) {
      if (k !== "todos" && !cont[k]) continue;
      const b = el("button", { className: S.filtro === k ? "ativo" : "", textContent: k === "todos" ? "Todos" : `${ROTULOS[k]} ${cont[k]}` });
      b.onclick = () => { S.filtro = k; renderResultados(); };
      $("#filtros").append(b);
    }
    const itens = [
      ...e.resultados.map((r) => ({ ...r, tipo: ROTULOS[r.classificacao] ? r.classificacao : "outro" })),
      ...e.porcentagem.map((p) => ({ ...p, tipo: "porcentagem", cobrancas: [] })),
    ].filter((x) => S.filtro === "todos" || x.tipo === S.filtro);
    for (const r of itens) {
      const det = r.tipo === "porcentagem" ? "Porcentagem = SIM (não conferido no Asaas)"
        : r.tipo === "nao_encontrado" ? M.MOTIVOS[r.busca] + ((r.detalhe || []).length ? "\n" + r.detalhe.join("\n") : "")
        : r.cobrancas.map((c) => `${c.situacao} · ${c.valor} · ${c.cliente}`).join("\n") + (r.confirmar_nome ? "\n⚠️ Confirmar: achado por nome aproximado" : "");
      const c = el("div", { className: "cartao c-" + r.tipo },
        el("div", { className: "nome", textContent: r.nome }),
        el("div", { className: "det", textContent: `${ROTULOS[r.tipo]} · venc. ${R.dataBr(r.vencimento)} · ${r.status_clickup || ""}` }),
        el("div", { className: "det", style: "white-space:pre-wrap", textContent: det }));
      const ls = el("div");
      ls.append(link(r.url, "Abrir no ClickUp"));
      for (const cb of r.cobrancas || []) if (cb.link) ls.append(link(cb.link, "Abrir fatura"));
      c.append(ls);
      lista.append(c);
    }
  }

  function botaoCopiar(texto, rotulo = "📋 Copiar") {
    const b = el("button", { className: "secundario", textContent: rotulo });
    b.onclick = async () => { await navigator.clipboard.writeText(texto); b.textContent = "✓ Copiado"; setTimeout(() => { b.textContent = rotulo; }, 1500); };
    return b;
  }

  function renderMensagens() {
    const lista = $("#listaMensagens");
    lista.replaceChildren();
    $("#qtdMsgs").textContent = S.mensagens.length ? `${S.mensagens.length} mensagem(ns)` : "Nenhuma mensagem gerada.";
    for (const m of S.mensagens) {
      lista.append(el("div", { className: "cartao" }, el("div", { className: "nome", textContent: m.nome }),
        el("div", { className: "msg", textContent: m.texto }), botaoCopiar(m.texto)));
    }
  }

  function renderAtualizar() {
    const lista = $("#listaAtualizar");
    lista.replaceChildren();
    for (const it of S.plano) {
      if (it._marcado === undefined) it._marcado = true;
      const cb = el("input", { type: "checkbox", checked: it._marcado, disabled: !!it._feito });
      cb.onchange = () => { it._marcado = cb.checked; };
      const res = it._resultado ? el("div", { className: it._feito ? "res-ok" : "res-erro", textContent: it._resultado }) : "";
      lista.append(el("div", { className: "cartao item-up c-" + (it.motivo === "pago" ? "pago" : "porcentagem") }, cb,
        el("div", {}, el("div", { className: "nome", textContent: it.nome }),
          el("div", { className: "det", textContent: `${it.motivo} · ${R.dataBr(it.vencimento)} → ${R.dataBr(it.nova_data)}` }), res)));
    }
    $("#aplicar").hidden = !S.plano.length;
  }

  // ------------------------------------------------------------ configurações
  async function carregarConfig() {
    const cfg = await Arm.config(), mapa = await Arm.mapa();
    $("#cfgUrl").value = cfg.clickup_url_lista || "";
    $("#cfgStatus").value = (cfg.status_alvo || []).join("\n");
    $("#cfgModelo").value = cfg.modelo_mensagem || "";
    $("#cfgModelo2").value = cfg.modelo_mensagem_sem_juros || "";
    $("#cfgAsaas").value = cfg.asaas_base || "";
    $("#cfgMapa").value = Object.entries(mapa).map(([k, v]) => `${JSON.stringify(k)}: ${JSON.stringify(v)}`).join(",\n");
  }

  async function salvarConfig() {
    let mapa;
    try {
      const txt = $("#cfgMapa").value.trim().replace(/,\s*$/, "");
      mapa = txt ? JSON.parse(txt.startsWith("{") ? txt : "{" + txt + "}") : {};
      delete mapa._explicacao;
    } catch (e) {
      $("#cfgAviso").textContent = "⚠️ O quadro de nomes tem um erro de formato. Cada linha: \"Nome no ClickUp\": \"Nome no Asaas\",";
      return;
    }
    const cfg = {
      clickup_url_lista: $("#cfgUrl").value.trim(),
      status_alvo: $("#cfgStatus").value.split("\n").map((s) => s.trim()).filter(Boolean),
      modelo_mensagem: $("#cfgModelo").value.trim(),
      modelo_mensagem_sem_juros: $("#cfgModelo2").value.trim(),
      asaas_base: $("#cfgAsaas").value.trim() || self.CONFIG_PADRAO.asaas_base,
    };
    await Arm.gravar("config", cfg);
    await Arm.gravar("mapa", mapa);
    await carregarConfig();
    $("#cfgAviso").textContent = "✓ Salvo!";
    setTimeout(() => { $("#cfgAviso").textContent = ""; }, 2500);
  }

  // ------------------------------------------------------------ início
  async function iniciar() {
    document.querySelectorAll("#abas button").forEach((b) => { b.onclick = () => irPara(b.dataset.aba); });
    document.querySelectorAll("#atalhos button").forEach((b) => {
      b.onclick = () => { bolha("eu", b.textContent.replace(/^\S+\s/, "")); executar({ acao: b.dataset.cmd }, b.textContent); };
    });
    $("#formCmd").onsubmit = async (ev) => {
      ev.preventDefault();
      const t = $("#cmd").value.trim();
      if (!t) return;
      $("#cmd").value = "";
      bolha("eu", t);
      executar(await interpretar(t), t);
    };
    $("#parar").onclick = () => { S.cancelar = true; status("Parando no próximo passo..."); };
    $("#aplicar").onclick = aplicarMarcados;
    $("#salvarConfig").onclick = salvarConfig;
    $("#copiarTodas").onclick = () => navigator.clipboard.writeText(S.mensagens.map((m) => m.texto).join("\n\n"));
    $("#copiarRelatorio").onclick = () => S.estado && navigator.clipboard.writeText(M.relatorioTexto(S.estado));

    await carregarConfig();
    S.estado = await Arm.estado();
    renderResultados();
    renderAtualizar();
    prepararIA();
    diz("Oi! Sou a assistente de cobranças da KAES. 👋\nO que vamos fazer? Use os botões ou escreva do seu jeito.");
    if (!(await Arm.config()).clickup_url_lista) {
      diz("Primeira vez por aqui: abra ⚙️ Configurações, cole o link da sua lista do ClickUp (aba “Visão Geral”) e clique em Salvar.");
    }
  }

  iniciar();
  self.__painel = { Arm, executar, interpretar, S }; // usado nos testes automáticos
})();
