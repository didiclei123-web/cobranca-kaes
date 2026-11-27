/* Testes da lógica da extensão (rodar: node testes-extensao/teste_logica.js). Sem internet. */
const R = require("../extensao/regras.js");
const Motor = require("../extensao/motor.js");
const PADRAO = require("../extensao/padroes.js");

let falhas = 0;
function checar(cond, msg) {
  console.log((cond ? "OK   " : "FALHOU ") + msg);
  if (!cond) falhas++;
}

// ---------------------------------------------------------------- regras
checar(R.lerData("20/11/26") === "2026-11-20", "lê dd/mm/aa");
checar(R.lerData("5/12/2026") === "2026-12-05", "lê d/mm/aaaa");
checar(R.lerData("há 2 dias") === null, "ignora texto relativo");
checar(R.lerData("31/02/2026") === null, "rejeita data inválida");
checar(R.maisUmMes("2026-11-20") === "2026-12-20", "+1 mês");
checar(R.maisUmMes("2026-12-15") === "2027-01-15", "+1 mês virando o ano");
checar(R.maisUmMes("2027-01-31") === "2027-02-28", "+1 mês em dia 31");
checar(R.dataBr("2026-12-20", true) === "20/12/26", "data curta");

let t = R.termosDeBusca("[Luiz Augusto] Moto Show Elias (ASAAS: Luiz Augusto)", {});
checar(t[0] === "Luiz Augusto" && t.includes("Moto Show Elias"), "termos com ASAAS/colchete: " + JSON.stringify(t));
t = R.termosDeBusca("Sortudo da Rifa - Marcos Dantas", {});
checar(JSON.stringify(t) === JSON.stringify(["Sortudo da Rifa", "Marcos Dantas"]), "termos por partes");
t = R.termosDeBusca("Lucas show premiações", { "Lucas show premiações": "Lucas Andrade de Sousa" });
checar(t[0] === "Lucas Andrade de Sousa", "mapa tem prioridade");
t = R.termosDeBusca("[Luiz Augusto] Mateus Moura Viana [Mensalista]", {});
checar(!t.includes("Mensalista") && t.includes("Mateus Moura Viana"), "ignora [Mensalista]");

checar(R.primeiroNome("Sortudo da Rifa - Marcos Dantas") === "Marcos", "primeiro nome");
checar(R.primeiroNome("[Luiz Augusto] Moto Show Elias (ASAAS: Luiz Augusto)") === "Luiz", "primeiro nome via ASAAS");
checar(R.primeiroNome("anderson") === "Anderson", "primeiro nome com maiúscula");
checar(R.classificarSituacao("Confirmada") === "pago", "cartão confirmado = pago");
checar(R.classificarSituacao("Vencida") === "inadimplente", "vencida = inadimplente");

const P = R.interpretarPalavrasChave;
checar(P("confere quem não pagou").acao === "conferir", "comando conferir");
checar(P("quem ta devendo?").acao === "conferir", "comando informal 'quem ta devendo'");
checar(P("gera as mensagens de cobrança").acao === "mensagens", "comando mensagens");
const c = P("faz uma mensagem para Anderson, venceu 20/11/2026 mas foi alterada sem juros");
checar(c.acao === "mensagem_cliente" && c.cliente === "anderson" && c.data_original === "20/11/2026" && c.sem_juros,
  "mensagem para cliente: " + JSON.stringify(c));
checar(P("marca os pagos e muda a data no clickup").acao === "atualizar", "comando atualizar");
checar(P("para").acao === "parar", "comando parar");

// ---------------------------------------------------------------- motor com navegador simulado
const HOJE = R.hoje();
const D = (n) => { const d = new Date(); d.setDate(d.getDate() - n); return R.hoje(d); };

const TAREFAS = [
  ["Sortudo da Rifa - Marcos Dantas", "renovação encaminhada", D(12), "", "PAGO"],
  ["Paulo Vítor Souza Lima - Paulo Som", "para renovar", D(7), "", "PAGO"],
  ["Zeca Premios - Davi Alves Barros", "para renovar", D(38), "", "INADIMPLENTE"],
  ["[Luiz Augusto] Mateus Moura Viana [Mensalista]", "para renovar", D(7), "", "INADIMPLENTE"],
  ["Lucas show premiações", "mensalistas - ativos", D(2), "", "PAGO"],
  ["XyzPremios - Anderson Silva Gomes", "mensalistas - ativos", D(7), "", "PAGO"],
  ["Campeões da Pista - Daniel Alves de Souza Filho", "mensalistas - ativos", D(12), "SIM", "PAGO"],
  ["ABPremiações - Leandro Lopes", "mensalistas - ativos", D(-13), "SIM", "PAGO"],
  ["Fulano Premios", "mensalistas - ativos", null, "", ""],
];
const ASAAS = [
  ["ALFA PROMOCOES LTDA - Sortudo/Sortudo - Marcos", "R$ 4.000,00", D(12), "Vencida"],
  ["ALFA PROMOCOES LTDA - Sortudo/Sortudo - Marcos", "R$ 4.000,00", D(-18), "Aguardando pagamento"],
  ["PAULOSOM PRODUCOES LTDA", "R$ 3.000,00", D(7), "Recebida"],
  ["DAVI ALVES BARROS", "R$ 2.263,79", D(38), "Confirmada"],
  ["MATEUS MOURA VIANA", "R$ 2.500,00", D(17), "Vencida"],
  ["LUCAS ANDRADE DE SOUSA", "R$ 4.000,00", D(2), "Recebida"],
];

class DriverFalso {
  constructor() { this.alteracoes = []; }
  async loginClickup() {}
  async loginAsaas() {}
  async listarTarefasClickup(alvo) {
    const a = new Set(alvo.map(R.semAcento));
    return TAREFAS.map((x, i) => ({ nome: x[0], url: "t/" + i, status: x[1] })).filter((x) => a.has(R.semAcento(x.status)));
  }
  async lerTarefa(url) {
    const x = TAREFAS[Number(url.split("/")[1])];
    return { vencimento: x[2], porcentagem: x[3], status_pagamento: x[4] };
  }
  async buscarCobrancas(termo) {
    const tt = R.semAcento(termo);
    return ASAAS.map((x, i) => ({ indice: i, cliente: x[0], valor: x[1], descricao: "", vencimento: x[2], icones: [], url_busca: "b" }))
      .filter((l) => R.semAcento(l.cliente).includes(tt));
  }
  async detalharCobranca(l) {
    const x = ASAAS[l.indice];
    return { situacao: x[3], cliente: x[0], link: "https://www.asaas.com/i/" + l.indice, url_cobranca: "s" };
  }
  async alterarTarefa(url, nova, pago) { this.alteracoes.push([url, nova, pago]); return []; }
}

class ArmFalso {
  constructor() { this.estado = null; }
  async config() { return { ...PADRAO, clickup_url_lista: "x" }; }
  async mapa() { return { "Lucas show premiações": "Lucas Andrade de Sousa" }; }
  async salvarEstado(e) { this.estado = JSON.parse(JSON.stringify(e)); }
}

(async () => {
  const drv = new DriverFalso(), arm = new ArmFalso();
  const estado = await Motor.conferir(drv, arm);
  const por = Object.fromEntries(estado.resultados.map((r) => [r.nome, r]));
  checar(por["Sortudo da Rifa - Marcos Dantas"].classificacao === "inadimplente", "vencido = inadimplente");
  checar(por["Sortudo da Rifa - Marcos Dantas"].cobrancas.length === 1, "sem cobrança duplicada");
  checar(por["Paulo Vítor Souza Lima - Paulo Som"].classificacao === "pago", "nome diferente no Asaas = pago");
  checar(por["Zeca Premios - Davi Alves Barros"].classificacao === "pago", "cartão confirmado = pago");
  checar(por["[Luiz Augusto] Mateus Moura Viana [Mensalista]"].busca === "sem_data", "sem cobrança na data");
  checar(por["Lucas show premiações"].classificacao === "pago", "achado via mapa");
  checar(por["XyzPremios - Anderson Silva Gomes"].classificacao === "nao_encontrado", "não encontrado");
  checar(estado.porcentagem.length === 1, "porcentagem: só o vencido");
  checar(JSON.stringify(estado.sem_data) === JSON.stringify(["Fulano Premios"]), "sem data listado");
  checar(arm.estado && arm.estado.resultados.length === 6, "estado salvo");
  checar(Motor.relatorioTexto(estado).includes("INADIMPLENTES (1)"), "relatório em texto");

  const msgs = await Motor.mensagensInadimplentes(estado, arm);
  checar(msgs.length === 1 && msgs[0].texto.startsWith("Olá, Marcos!") && msgs[0].texto.includes("asaas.com/i/0")
    && msgs[0].texto.includes(R.dataBr(D(12))), "mensagem com nome, data e link");

  const plano = Motor.planoAtualizacao(estado);
  checar(plano.length === 4, "plano: 3 pagos + 1 porcentagem");
  checar(plano.every((p) => p.nova_data === R.maisUmMes(p.vencimento)), "nova data = +1 mês");
  const feitos = [];
  await Motor.aplicar(drv, arm, estado, plano, { aoTerminarItem: (i, p) => feitos.push(p.length) });
  checar(drv.alteracoes.length === 4 && drv.alteracoes.every((a) => a[2]), "4 alterações com PAGO");
  checar(Motor.planoAtualizacao(arm.estado).length === 0, "não altera duas vezes");

  const linhas = await Motor.buscarCobrancasCliente(drv, arm, "Marcos");
  checar(linhas.length === 2 && linhas[0].vencimento > linhas[1].vencimento, "cobranças do cliente, mais nova primeiro");
  const venc = linhas.find((l) => l.vencimento === D(12));
  let m = await Motor.mensagemDaCobranca(drv, arm, "Marcos", venc);
  checar(m.situacao === "Vencida" && m.texto.startsWith("Olá, Marcos!"), "mensagem avulsa");
  m = await Motor.mensagemDaCobranca(drv, arm, "Marcos", venc, "20/11/2026", true);
  checar(m.texto.includes("sem cobrança de juros") && m.texto.includes("20/11/2026"), "mensagem sem juros");

  let parou = false;
  try { await Motor.conferir(drv, arm, { cancelado: () => true }); } catch (e) { parou = e instanceof Motor.Cancelado; }
  checar(parou, "botão parar interrompe");

  console.log(falhas ? `\n${falhas} FALHA(S)` : "\nTodos os testes da lógica passaram.");
  process.exit(falhas ? 1 : 0);
})();
