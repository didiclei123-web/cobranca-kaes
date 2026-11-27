"""
Sites FALSOS que imitam a estrutura do ClickUp e do Asaas (para testar a extensão sem conta real).
- ClickUp: lista com rolagem "virtual" (só desenha as linhas visíveis), página de tarefa com
  botão de vencimento, campo de data que SÓ aceita teclado de verdade (isTrusted), campos com aria-label.
- Asaas: tabela feita com componentes em shadow DOM (atlas-*), página de detalhe com Situação e link.
Os nomes de clientes são inventados.
"""
import json
import sys
import threading
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HOJE = date.today()


def D(n):
    return HOJE - timedelta(days=n)


def br(d, curto=False):
    return d.strftime("%d/%m/%y" if curto else "%d/%m/%Y")


TAREFAS = {  # id: nome, status, vencimento, porcentagem, status_pagamento
    "a1": ["Sortudo da Rifa - Marcos Dantas", "renovação encaminhada", D(12), "", "PAGO"],
    "a2": ["Paulo Vítor Souza Lima - Paulo Som", "para renovar", D(7), "", "PAGO"],
    "a3": ["Zeca Premios - Davi Alves Barros", "para renovar", D(38), "", "INADIMPLENTE"],
    "a4": ["[Luiz Augusto] Mateus Moura Viana [Mensalista]", "para renovar", D(7), "", "INADIMPLENTE"],
    "a5": ["Lucas show premiações", "mensalistas - ativos", D(2), "", "PAGO"],
    "a6": ["XyzPremios - Anderson Silva Gomes", "mensalistas - ativos", D(7), "", "PAGO"],
    "a7": ["Campeões da Pista - Daniel Alves de Souza Filho", "mensalistas - ativos", D(12), "SIM", "PAGO"],
    "a8": ["ABPremiações - Leandro Lopes", "mensalistas - ativos", D(-13), "SIM", "PAGO"],
    "a9": ["Fulano Premios", "mensalistas - ativos", None, "", ""],
}
# muitas tarefas em outros status, para forçar a rolagem da lista
for i in range(30):
    TAREFAS[f"z{i}"] = [f"Cliente Pausado {i:02d}", "pausado", D(40), "", "PAGO"]
for i in range(6):
    TAREFAS[f"m{i}"] = [f"Mensalista em dia {i}", "mensalistas - ativos", D(-20 - i), "", "PAGO"]

COBRANCAS = [  # id, cliente, valor, vencimento, situacao, icone
    ["c1", "ALFA PROMOCOES LTDA - Sortudo/Sortudo - Marcos", "R$ 4.000,00", D(12), "Vencida", "x-filled"],
    ["c2", "ALFA PROMOCOES LTDA - Sortudo/Sortudo - Marcos", "R$ 4.000,00", D(-18), "Aguardando pagamento", "clock-filled"],
    ["c3", "PAULOSOM PRODUCOES LTDA", "R$ 3.000,00", D(7), "Recebida", "check-filled"],
    ["c4", "DAVI ALVES BARROS", "R$ 2.263,79", D(38), "Confirmada", "clock-filled"],
    ["c5", "MATEUS MOURA VIANA", "R$ 2.500,00", D(17), "Vencida", "x-filled"],
    ["c6", "LUCAS ANDRADE DE SOUSA", "R$ 4.000,00", D(2), "Recebida", "check-filled"],
]

ALTERACOES = []  # registro do que a extensão alterou


def sem_acento(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)).lower()


PAG_LISTA = """<!doctype html><meta charset=utf-8><title>Lista</title>
<style>#viewport{height:320px;overflow-y:auto;border:1px solid #ccc} .row{height:40px}</style>
<div id=viewport><div id=spacer style="position:relative"></div></div>
<script>
const T = __TAREFAS__; const H = 40;
const sp = document.getElementById('spacer'), vp = document.getElementById('viewport');
sp.style.height = (T.length*H) + 'px';
function desenhar(){
  const ini = Math.max(0, Math.floor(vp.scrollTop/H)-2), fim = Math.min(T.length, ini+12);
  sp.innerHTML = '';
  for (let i=ini;i<fim;i++){ const t=T[i];
    const d = document.createElement('div'); d.className='row'; d.style.cssText='position:absolute;top:'+(i*H)+'px';
    d.innerHTML = '<cu-task-name-cell><div>Cliente '+t.status.toUpperCase()+'</div><div>Status atual: '+t.status+'</div>'+
      '<a data-test="task-row-main__link" href="/clickup/t/'+t.id+'">'+t.nome+(i%3==0?'<div>Descrição</div>':'')+'</a></cu-task-name-cell>';
    sp.appendChild(d);
  }
}
vp.addEventListener('scroll', desenhar); setTimeout(desenhar, 600);
</script>"""

PAG_TAREFA = """<!doctype html><meta charset=utf-8><title>__NOME__</title>
<div data-test="view-task__body">
 <h1>__NOME__</h1>
 <div data-test="task-hero-section__dates">
  <button data-test="task-dates-display-button"><svg><use href="#cu3-icon-dateStart"></use></svg><span>Início</span></button>
  __BOTAO_VENC__
 </div>
 <div id=picker></div>
 <div aria-label="__ROT_PORC__" data-test="dropdown-labels-menu__toggle">__PORC__</div>
 <div id=pag aria-label="__ROT_PAG__" data-test="custom-field-type-dropdown__dropdown-toggle">__PAG__</div>
 <div id=menu></div>
</div>
<script>
const ID = "__ID__";
let venc = "__VENC__";
const btn = document.getElementById('venc');
if (btn) btn.addEventListener('click', () => {
  const p = document.getElementById('picker');
  if (p.innerHTML) { p.innerHTML=''; return; }
  p.innerHTML = '<input placeholder="Data inicial" data-test="date-nlp-input__calendar-input"><input id=iv placeholder="Data de vencimento" data-test="date-nlp-input__calendar-input">';
  const iv = document.getElementById('iv'); iv.value = venc;
  iv.addEventListener('keydown', async (e) => {
    if (e.key === 'Escape') { p.innerHTML=''; return; }
    if (e.key !== 'Enter') return;
    if (!e.isTrusted) return;               // igual ao ClickUp: ignora teclado "falso"
    const r = await fetch('/api/data?id='+ID+'&v='+encodeURIComponent(iv.value)); venc = await r.text();
    btn.querySelector('span').textContent = venc.slice(0,5); p.innerHTML='';
  });
});
document.getElementById('pag').addEventListener('click', () => {
  document.getElementById('menu').innerHTML = ['–','PAGO','INADIMPLENTE','CRÍTICO'].map(o =>
    '<cu-select-option role=option data-test="custom-fields__select-menu_dropdown-item-'+o+'">'+o+'</cu-select-option>').join('');
  document.querySelectorAll('#menu [role=option]').forEach(o => o.addEventListener('click', async () => {
    const v = o.textContent; await fetch('/api/pago?id='+ID+'&v='+encodeURIComponent(v));
    const pg = document.getElementById('pag'); pg.setAttribute('aria-label','Campo personalizado Status do Pagamento. '+v); pg.textContent=v;
    document.getElementById('menu').innerHTML='';
  }));
});
</script>"""

PAG_ASAAS_LISTA = """<!doctype html><meta charset=utf-8><title>Asaas - Lista de cobranças</title>
<atlas-screen></atlas-screen>
<script>
const LINHAS = __LINHAS__;
class Tabela extends HTMLElement { connectedCallback(){ this.attachShadow({mode:'open'}); } }
customElements.define('atlas-screen', Tabela);
const host = document.querySelector('atlas-screen');
setTimeout(() => {
  if (!LINHAS.length) { host.shadowRoot.innerHTML = '<atlas-empty-state><p>Nenhuma cobrança foi encontrada</p></atlas-empty-state>'; return; }
  host.shadowRoot.innerHTML = '<atlas-table-row><atlas-table-col>Nome</atlas-table-col></atlas-table-row>' +
    LINHAS.map(l => '<atlas-table-row><atlas-table-col><atlas-icon name="user-filled"></atlas-icon>'+l.cliente+'</atlas-table-col>'+
      '<atlas-table-col>'+l.valor+'</atlas-table-col><atlas-table-col>Descrição</atlas-table-col><atlas-table-col>Pix</atlas-table-col>'+
      '<atlas-table-col data-id="'+l.id+'">'+l.venc+' <atlas-icon name="'+l.icone+'"></atlas-icon></atlas-table-col>'+
      '<atlas-table-col></atlas-table-col></atlas-table-row>').join('');
  host.shadowRoot.querySelectorAll('atlas-table-col[data-id]').forEach(c =>
    c.addEventListener('click', () => { location.href = '/payment/show/' + c.dataset.id; }));
}, 900);
</script>"""

PAG_ASAAS_DET = """<!doctype html><meta charset=utf-8><title>Asaas - Visualização de Pagamento</title>
<div>Dados da cobrança</div><div>Situação</div><div>__SIT__</div>
<div>Cliente</div><div>__CLI__</div>
<div>Número da fatura</div><div>123 - <a href="https://www.asaas.com/i/__ID__fatura">Visualizar fatura</a></div>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def responder(self, corpo, tipo="text/html; charset=utf-8"):
        b = corpo.encode()
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/clickup/lista":
            lista = [{"id": k, "nome": v[0], "status": v[1]} for k, v in TAREFAS.items()]
            return self.responder(PAG_LISTA.replace("__TAREFAS__", json.dumps(lista, ensure_ascii=False)))
        if u.path.startswith("/clickup/t/"):
            tid = u.path.rsplit("/", 1)[1]
            nome, st, venc, porc, pag = TAREFAS[tid]
            botao = ('<button id=venc data-test="task-dates-display-button"><svg><use href="#cu3-icon-dateDue"></use></svg>'
                     f'<span>{br(venc)[:5]}</span></button>') if venc else ""
            return self.responder(PAG_TAREFA.replace("__NOME__", nome).replace("__ID__", tid)
                                  .replace("__BOTAO_VENC__", botao).replace("__VENC__", br(venc, True) if venc else "")
                                  .replace("__ROT_PORC__", f"Campo personalizado Porcentagem. {porc}" if porc
                                           else "Definir valor para o campo personalizado Porcentagem")
                                  .replace("__PORC__", porc or "–")
                                  .replace("__ROT_PAG__", f"Campo personalizado Status do Pagamento. {pag}" if pag
                                           else "Definir valor para o campo personalizado Status do Pagamento")
                                  .replace("__PAG__", pag or "–"))
        if u.path == "/api/data":
            d, m, a = q["v"].split("/")
            nova = date(2000 + int(a) if len(a) == 2 else int(a), int(m), int(d))
            TAREFAS[q["id"]][2] = nova
            ALTERACOES.append(("data", q["id"], br(nova)))
            return self.responder(br(nova, True), "text/plain")
        if u.path == "/api/pago":
            TAREFAS[q["id"]][4] = q["v"]
            ALTERACOES.append(("pago", q["id"], q["v"]))
            return self.responder("ok", "text/plain")
        if u.path == "/api/estado":
            return self.responder(json.dumps({"tarefas": {k: [v[0], v[1], br(v[2]) if v[2] else None, v[3], v[4]]
                                                          for k, v in TAREFAS.items()}, "alteracoes": ALTERACOES},
                                             ensure_ascii=False), "application/json")
        if u.path == "/payment/list":
            termo = sem_acento(q.get("customerAccountText", ""))
            linhas = [{"id": c[0], "cliente": c[1], "valor": c[2], "venc": br(c[3]), "icone": c[5]}
                      for c in COBRANCAS if termo and termo in sem_acento(c[1])]
            return self.responder(PAG_ASAAS_LISTA.replace("__LINHAS__", json.dumps(linhas, ensure_ascii=False)))
        if u.path.startswith("/payment/show/"):
            cid = u.path.rsplit("/", 1)[1]
            c = next(x for x in COBRANCAS if x[0] == cid)
            return self.responder(PAG_ASAAS_DET.replace("__SIT__", c[4]).replace("__CLI__", c[1]).replace("__ID__", cid))
        self.send_response(404)
        self.end_headers()


def iniciar(porta=8765):
    srv = ThreadingHTTPServer(("127.0.0.1", porta), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    iniciar(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
    print("Sites falsos em http://localhost:8765 (Ctrl+C para sair)")
    threading.Event().wait()
