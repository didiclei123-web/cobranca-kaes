/*
 * Regras de negócio: datas, nomes, correspondência ClickUp x Asaas, mensagens
 * e entendimento de comandos por palavras-chave. Não mexe em navegador.
 * Datas são guardadas como texto "AAAA-MM-DD" (fácil de comparar e salvar).
 */
(function (raiz) {
  "use strict";

  const PALAVRAS_GENERICAS = new Set([
    "premios", "premio", "premiacoes", "premiacao", "rifa", "rifas", "acoes", "acao",
    "sorte", "sorteio", "sorteios", "mensalista", "asaas", "ltda", "the", "dos", "das",
    "de", "da", "do", "e", "loco", "brasil", "oficial",
  ]);

  // ------------------------------------------------------------------ texto
  function semAcento(txt) {
    return String(txt || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  }

  function capitalizar(p) {
    return p ? p.charAt(0).toUpperCase() + p.slice(1).toLowerCase() : p;
  }

  // ------------------------------------------------------------------ datas
  const pad = (n) => String(n).padStart(2, "0");

  function isoDe(ano, mes, dia) {
    const d = new Date(Date.UTC(ano, mes - 1, dia));
    if (d.getUTCFullYear() !== ano || d.getUTCMonth() !== mes - 1 || d.getUTCDate() !== dia) return null;
    return `${ano}-${pad(mes)}-${pad(dia)}`;
  }

  /** "20/11/26", "5/12/2026" -> "2026-11-20". Texto sem data -> null. */
  function lerData(txt) {
    if (!txt) return null;
    if (/^\d{4}-\d{2}-\d{2}$/.test(txt)) return txt;
    const m = String(txt).match(/(\d{1,2})\/(\d{1,2})\/(\d{2,4})/);
    if (!m) return null;
    let [d, mes, a] = m.slice(1).map(Number);
    if (a < 100) a += 2000;
    return isoDe(a, mes, d);
  }

  function dataBr(iso, anoCurto = false) {
    if (!iso) return "";
    const [a, m, d] = iso.split("-");
    return `${d}/${m}/${anoCurto ? a.slice(2) : a}`;
  }

  function maisUmMes(iso) {
    let [a, m, d] = iso.split("-").map(Number);
    m += 1;
    if (m > 12) { m = 1; a += 1; }
    const ultimo = new Date(Date.UTC(a, m, 0)).getUTCDate();
    return isoDe(a, m, Math.min(d, ultimo));
  }

  function hoje(agora = new Date()) {
    return `${agora.getFullYear()}-${pad(agora.getMonth() + 1)}-${pad(agora.getDate())}`;
  }

  // ------------------------------------------------------------------ nomes
  function unicos(lista) {
    const vistos = new Set(), saida = [];
    for (const t of lista) {
      const k = semAcento(t);
      if (k && !vistos.has(k)) { vistos.add(k); saida.push(t); }
    }
    return saida;
  }

  /** Termos para pesquisar o cliente no Asaas, do mais confiável ao menos. */
  function termosDeBusca(nomeClickup, mapa = {}) {
    const termos = [];
    const valor = mapa[nomeClickup];
    if (valor) termos.push(...(Array.isArray(valor) ? valor : [valor]));
    const m = nomeClickup.match(/\(\s*asaas\s*:\s*([^)]+)\)/i);
    if (m) termos.push(m[1].trim());
    for (const c of nomeClickup.matchAll(/\[([^\]]+)\]/g)) {
      if (!["mensalista", "a vista + parcelado"].includes(semAcento(c[1]))) termos.push(c[1].trim());
    }
    const limpo = nomeClickup.replace(/\([^)]*\)|\[[^\]]*\]/g, " ");
    for (let parte of limpo.split(/\s+-\s+|\//)) {
      parte = parte.replace(/\s+/g, " ").replace(/^[\s\-@]+|[\s\-@]+$/g, "");
      if (parte.length >= 3 && !PALAVRAS_GENERICAS.has(semAcento(parte))) termos.push(parte);
    }
    return unicos(termos);
  }

  /** Última tentativa: palavras soltas (resultado marcado para conferir). */
  function palavrasReserva(nomeClickup) {
    const limpo = nomeClickup.replace(/\([^)]*\)|\[[^\]]*\]|@\S+/g, " ");
    const saida = [];
    for (const p of limpo.match(/[A-Za-zÀ-ÿ]{4,}/g) || []) {
      if (!PALAVRAS_GENERICAS.has(semAcento(p)) && !saida.includes(p)) saida.push(p);
    }
    return saida;
  }

  /** "Sortudo da Rifa - Marcos Dantas" -> "Marcos". */
  function primeiroNome(nomeClickup) {
    const m = nomeClickup.match(/\(\s*asaas\s*:\s*([^)]+)\)/i);
    let base = m ? m[1] : nomeClickup.replace(/\[[^\]]*\]/g, "").split(/\s+-\s+/).pop();
    base = base.replace(/\([^)]*\)/g, "");
    const palavras = base.match(/[A-Za-zÀ-ÿ]+/g);
    return palavras ? capitalizar(palavras[0]) : nomeClickup.trim();
  }

  function classificarSituacao(situacao) {
    const s = semAcento(situacao);
    if (s.startsWith("recebida") || s.startsWith("confirmada")) return "pago";
    if (s === "vencida") return "inadimplente";
    if (s.startsWith("aguardando")) return "aguardando";
    return "outro";
  }

  /** linhas: [{cliente, vencimento(iso), ...}] -> {status, linhas} */
  function escolherCobranca(linhas, dataAlvo) {
    if (!linhas.length) return { status: "nao_encontrado", linhas: [] };
    const naData = linhas.filter((l) => l.vencimento === dataAlvo);
    if (!naData.length) return { status: "sem_data", linhas };
    const clientes = new Set(naData.map((l) => semAcento(l.cliente)));
    return { status: clientes.size === 1 ? "ok" : "ambiguo", linhas: naData };
  }

  // ------------------------------------------------------------------ mensagens
  function montarMensagem(modelo, nome, data, link, novaData = "") {
    return modelo
      .split("[NOME DO CLIENTE]").join(nome)
      .split("[DATA DE VENCIMENTO]").join(data)
      .split("[NOVA DATA]").join(novaData)
      .split("[LINK DE COBRANÇA]").join(link);
  }

  // ------------------------------------------------------------------ comandos
  const ACOES = ["conferir", "mensagens", "atualizar", "mensagem_cliente", "ajuda", "parar"];

  function interpretarPalavrasChave(texto) {
    const t = semAcento(texto);
    const r = { acao: null, cliente: null, data_original: null, sem_juros: false };
    if (/\b(para|pare|parar|cancela|cancelar|interromp)\b/.test(t) && t.split(" ").length <= 3) {
      r.acao = "parar";
    } else if (/\b(ajuda|help|comandos|o que (voce|vc) faz)\b/.test(t)) {
      r.acao = "ajuda";
    } else if (/\b(atualiz|altera|marca|coloca|muda|empurra)/.test(t) &&
               /\b(pago|pagos|data|vencimento|porcentagem|clickup)/.test(t)) {
      r.acao = "atualizar";
    } else if (/\b(mensage(m|ns)|cobra|lembrete|texto)/.test(t)) {
      const m = (t + " ").match(/\b(?:para|pra|pro|ao)\s+(?:o |a )?([a-z0-9 ]{3,40}?)(?:,|\.|$| que | com | venc| sem )/);
      if (m && !/\b(todos|inadimplentes|vencidos|cobranca|cobrancas|clientes|eles|cada)\b/.test(m[1])) {
        r.acao = "mensagem_cliente";
        r.cliente = m[1].trim();
      } else {
        r.acao = "mensagens";
      }
    } else if (/\b(confer|verific|checa|analis|quem (pagou|nao pagou|deve|ta devendo|esta devendo)|vencid|inadimpl|relatorio|lista|devendo)/.test(t)) {
      r.acao = "conferir";
    }
    const d = lerData(texto);
    if (d) r.data_original = dataBr(d);
    r.sem_juros = /sem juros/.test(t);
    return r;
  }

  const Regras = {
    semAcento, lerData, dataBr, maisUmMes, hoje, termosDeBusca, palavrasReserva, primeiroNome,
    classificarSituacao, escolherCobranca, montarMensagem, interpretarPalavrasChave, ACOES,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = Regras;
  raiz.Regras = Regras;
})(typeof self !== "undefined" ? self : globalThis);
