/*
 * O passo a passo: conferir, mensagens, atualizar e mensagem para um cliente.
 * Recebe um "driver" (quem clica e lê as telas) e um "armazenamento".
 */
(function (raiz) {
  "use strict";
  const R = raiz.Regras || (typeof require !== "undefined" ? require("./regras.js") : null);

  const DICAS_ICONE = { "check-filled": "paga", "x-filled": "vencida", "clock-filled": "aguardando / cartão" };
  const MOTIVOS = {
    sem_data: "cliente achado, mas sem cobrança nessa data",
    ambiguo: "mais de um cliente com cobrança nessa data",
    nao_encontrado: "nenhuma cobrança encontrada",
  };

  class Cancelado extends Error { constructor() { super("Interrompido por você."); } }

  const chaveLinha = (l) => [R.semAcento(l.cliente), l.vencimento, l.valor, l.descricao].join("|");

  async function localizarNoAsaas(driver, nomeClickup, vencimento, mapa, checar) {
    const vistos = new Set(), linhas = [];
    for (const termo of R.termosDeBusca(nomeClickup, mapa)) {
      checar();
      for (const l of await driver.buscarCobrancas(termo)) {
        if (!vistos.has(chaveLinha(l))) { vistos.add(chaveLinha(l)); l.reserva = false; linhas.push(l); }
      }
      const r = R.escolherCobranca(linhas, vencimento);
      if (r.status === "ok") return r;
    }
    const r = R.escolherCobranca(linhas, vencimento);
    if (r.status === "nao_encontrado" || r.status === "sem_data") {
      const reserva = [], vistosR = new Set();
      for (const palavra of R.palavrasReserva(nomeClickup)) {
        checar();
        for (const l of await driver.buscarCobrancas(palavra)) {
          if (l.vencimento === vencimento && !vistosR.has(chaveLinha(l))) {
            vistosR.add(chaveLinha(l)); l.reserva = true; reserva.push(l);
          }
        }
      }
      const r2 = R.escolherCobranca(reserva, vencimento);
      if (r2.status === "ok" || r2.status === "ambiguo") return r2;
    }
    return r;
  }

  // ---------------------------------------------------------------- 1. Conferir
  async function conferir(driver, arm, { avisar = () => {}, progresso = () => {}, cancelado = () => false } = {}) {
    const checar = () => { if (cancelado()) throw new Cancelado(); };
    const cfg = await arm.config();
    const mapa = await arm.mapa();
    const dia = R.hoje();

    avisar("Lendo a lista do ClickUp...");
    await driver.loginClickup();
    const tarefas = await driver.listarTarefasClickup(cfg.status_alvo);
    avisar(`${tarefas.length} tarefas nos status escolhidos.`);

    const vencidos = [], porcentagem = [], semData = [];
    const total = Math.max(tarefas.length * 2, 1);
    for (let i = 0; i < tarefas.length; i++) {
      checar();
      const t = tarefas[i];
      progresso(i + 1, total, `ClickUp: ${t.nome}`);
      try {
        Object.assign(t, await driver.lerTarefa(t.url));
      } catch (e) {
        avisar(`! Falha ao ler "${t.nome}": ${e.message}`);
        continue;
      }
      if (!t.vencimento) semData.push(t);
      else if (t.vencimento < dia) (R.semAcento(t.porcentagem) === "sim" ? porcentagem : vencidos).push(t);
    }

    avisar(`${vencidos.length} vencidos para conferir no Asaas, ${porcentagem.length} de porcentagem.`);
    if (vencidos.length) await driver.loginAsaas();
    const resultados = [];
    for (let i = 0; i < vencidos.length; i++) {
      checar();
      const t = vencidos[i];
      progresso(tarefas.length + Math.round(((i + 1) * tarefas.length) / vencidos.length), total, `Asaas: ${t.nome}`);
      let achado;
      try {
        achado = await localizarNoAsaas(driver, t.nome, t.vencimento, mapa, checar);
      } catch (e) {
        if (e instanceof Cancelado) throw e;
        avisar(`! Falha no Asaas para "${t.nome}": ${e.message}`);
        achado = { status: "nao_encontrado", linhas: [] };
      }
      const r = {
        nome: t.nome, url: t.url, status_clickup: t.status, vencimento: t.vencimento,
        status_pagamento_clickup: t.status_pagamento || "", busca: achado.status,
        cobrancas: [], classificacao: null, confirmar_nome: false, detalhe: [],
      };
      if (achado.status === "ok") {
        for (const l of achado.linhas) {
          checar();
          const det = await driver.detalharCobranca(l);
          r.cobrancas.push({ cliente: det.cliente || l.cliente, valor: l.valor, situacao: det.situacao,
                             link: det.link || "", url: det.url_cobranca || "" });
          r.confirmar_nome = r.confirmar_nome || !!l.reserva;
        }
        const classes = r.cobrancas.map((c) => R.classificarSituacao(c.situacao));
        r.classificacao = classes.includes("inadimplente") ? "inadimplente"
          : classes.length && classes.every((c) => c === "pago") ? "pago" : classes[0] || "outro";
      } else {
        r.classificacao = "nao_encontrado";
        r.detalhe = achado.linhas.slice(0, 8).map((l) => `${l.cliente} — ${R.dataBr(l.vencimento) || "?"} — ${l.valor}`);
      }
      avisar(`${t.nome} → ${r.classificacao}`);
      resultados.push(r);
    }

    const estado = {
      data: dia, gerado_em: new Date().toISOString(), resultados,
      porcentagem: porcentagem.map((t) => ({ nome: t.nome, url: t.url, vencimento: t.vencimento,
                                            status_clickup: t.status, status_pagamento_clickup: t.status_pagamento || "" })),
      sem_data: semData.map((t) => t.nome), atualizados: [],
    };
    await arm.salvarEstado(estado);
    progresso(total, total, "Conferência concluída");
    return estado;
  }

  function relatorioTexto(estado) {
    const res = estado.resultados, out = [`RELATÓRIO DE COBRANÇAS — ${R.dataBr(estado.data)}`, "=".repeat(48)];
    const bloco = (titulo, itens, fmt) => {
      out.push(`\n${titulo} (${itens.length})`);
      if (itens.length) itens.forEach((x) => out.push(fmt(x))); else out.push("  —");
    };
    const cob = (r) => `  • ${r.nome} — venc. ${R.dataBr(r.vencimento)} — ` +
      r.cobrancas.map((c) => `${c.situacao} ${c.valor} (${c.cliente})`).join("; ") +
      (r.confirmar_nome ? "  [CONFIRMAR NOME]" : "");
    bloco("INADIMPLENTES", res.filter((r) => r.classificacao === "inadimplente"), cob);
    bloco("PAGOS", res.filter((r) => r.classificacao === "pago"), cob);
    bloco("AGUARDANDO / OUTROS", res.filter((r) => ["aguardando", "outro"].includes(r.classificacao)), cob);
    bloco("NÃO ENCONTRADOS NO ASAAS", res.filter((r) => r.classificacao === "nao_encontrado"),
      (r) => `  • ${r.nome} — venc. ${R.dataBr(r.vencimento)} — ${MOTIVOS[r.busca] || r.busca}` +
             (r.detalhe || []).map((d) => `\n      - ${d}`).join(""));
    bloco("PORCENTAGEM = SIM (não conferidos no Asaas)", estado.porcentagem,
      (p) => `  • ${p.nome} — venc. ${R.dataBr(p.vencimento)}`);
    if (estado.sem_data && estado.sem_data.length) bloco("SEM DATA DE VENCIMENTO", estado.sem_data, (n) => `  • ${n}`);
    return out.join("\n") + "\n";
  }

  // ---------------------------------------------------------------- 2. Mensagens
  async function mensagensInadimplentes(estado, arm) {
    const cfg = await arm.config();
    const saida = [];
    for (const r of estado.resultados) {
      if (r.classificacao !== "inadimplente") continue;
      for (const c of r.cobrancas) {
        if (R.classificarSituacao(c.situacao) === "inadimplente") {
          saida.push({ nome: r.nome, texto: R.montarMensagem(cfg.modelo_mensagem, R.primeiroNome(r.nome),
            R.dataBr(r.vencimento), c.link || "(link não encontrado)") });
        }
      }
    }
    return saida;
  }

  // ---------------------------------------------------------------- 3. Atualizar
  function planoAtualizacao(estado) {
    const feitos = new Set(estado.atualizados || []);
    const plano = [];
    for (const r of estado.resultados) {
      if (r.classificacao === "pago" && !feitos.has(r.url)) plano.push({ nome: r.nome, url: r.url, motivo: "pago", vencimento: r.vencimento });
    }
    for (const p of estado.porcentagem) {
      if (!feitos.has(p.url)) plano.push({ nome: p.nome, url: p.url, motivo: "porcentagem", vencimento: p.vencimento });
    }
    plano.forEach((it) => { it.nova_data = R.maisUmMes(it.vencimento); });
    return plano;
  }

  async function aplicar(driver, arm, estado, itens, { aoTerminarItem = () => {}, cancelado = () => false } = {}) {
    await driver.loginClickup();
    for (const item of itens) {
      if (cancelado()) throw new Cancelado();
      let problemas;
      try {
        problemas = await driver.alterarTarefa(item.url, item.nova_data, true);
      } catch (e) {
        problemas = [e.message];
      }
      if (!problemas.length) {
        (estado.atualizados = estado.atualizados || []).push(item.url);
        await arm.salvarEstado(estado);
      }
      aoTerminarItem(item, problemas);
    }
  }

  // ---------------------------------------------------------------- 4. Mensagem para um cliente
  async function buscarCobrancasCliente(driver, arm, cliente) {
    const mapa = await arm.mapa();
    let termos = [cliente];
    for (const [nomeCk, valor] of Object.entries(mapa)) {
      if (R.semAcento(nomeCk).includes(R.semAcento(cliente))) termos = [...(Array.isArray(valor) ? valor : [valor]), ...termos];
    }
    await driver.loginAsaas();
    const linhas = [], vistos = new Set();
    for (const termo of termos) {
      for (const l of await driver.buscarCobrancas(termo)) {
        const k = [l.cliente, l.vencimento, l.valor].join("|");
        if (!vistos.has(k)) {
          vistos.add(k);
          l.dica = (l.icones || []).map((x) => DICAS_ICONE[x]).find(Boolean) || "outra";
          linhas.push(l);
        }
      }
      if (linhas.length) break;
    }
    linhas.sort((a, b) => String(b.vencimento).localeCompare(String(a.vencimento)));
    return linhas;
  }

  async function mensagemDaCobranca(driver, arm, cliente, linha, dataOriginal = null, semJuros = false) {
    const cfg = await arm.config();
    const det = await driver.detalharCobranca(linha);
    const nome = R.primeiroNome(cliente);
    const dataCob = R.dataBr(linha.vencimento);
    const link = det.link || "(link não encontrado)";
    const texto = semJuros && dataOriginal
      ? R.montarMensagem(cfg.modelo_mensagem_sem_juros, nome, dataOriginal, link, dataCob)
      : R.montarMensagem(cfg.modelo_mensagem, nome, dataCob, link);
    return { situacao: det.situacao, texto };
  }

  const Motor = {
    conferir, relatorioTexto, mensagensInadimplentes, planoAtualizacao, aplicar,
    buscarCobrancasCliente, mensagemDaCobranca, localizarNoAsaas, MOTIVOS, DICAS_ICONE, Cancelado,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = Motor;
  raiz.Motor = Motor;
})(typeof self !== "undefined" ? self : globalThis);
