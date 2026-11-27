"""
Cobranças KAES — janela do programa.

Toda a parte de navegador roda numa "linha de trabalho" separada (o Playwright
precisa ficar sempre na mesma), e a janela só recebe avisos por uma fila.
"""
import json
import os
import queue
import sys
import threading
import traceback
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import base
import motor
import regras as R
from ia_local import IALocal

VERSAO = "1.0"

CORES = {
    "fundo": "#F5F6FA", "card": "#FFFFFF", "texto": "#1F2430", "suave": "#6B7280",
    "primaria": "#3B5BDB", "primaria_hover": "#2F4AC0",
    "inadimplente": "#FDE2E1", "pago": "#DDF5E3", "aguardando": "#FFF4D6",
    "nao_encontrado": "#EDE7F6", "porcentagem": "#E3F0FD", "outro": "#F1F1F1",
}
ROTULOS = {"inadimplente": "🔴 Inadimplente", "pago": "🟢 Pago", "aguardando": "🟡 Aguardando",
           "outro": "🟡 Outro", "nao_encontrado": "⚠️ Não encontrado", "porcentagem": "📊 Porcentagem"}


# ====================================================================== trabalhador
class Trabalhador(threading.Thread):
    """Executa as tarefas de navegador, uma de cada vez."""

    def __init__(self, ui):
        super().__init__(daemon=True)
        self.ui = ui
        self.tarefas = queue.Queue()
        self.nav = None

    def run(self):
        while True:
            funcao, args = self.tarefas.get()
            if funcao is None:
                break
            try:
                self.ui.evento("ocupado", True)
                funcao(*args)
            except Exception as e:
                self.ui.evento("log", "ERRO: " + "".join(traceback.format_exception_only(type(e), e)).strip())
                self.ui.evento("erro", str(e))
            finally:
                self.ui.evento("ocupado", False)
        if self.nav:
            try:
                self.nav.fechar()
            except Exception:
                pass

    def navegador(self):
        if self.nav is None:
            from navegador import Navegador
            self.ui.evento("log", "Abrindo o navegador...")
            self.nav = Navegador(base.carregar_config(),
                                 avisar=lambda t: self.ui.evento("log", t),
                                 pedir_login=self.ui.pedir_login_bloqueando)
            self.ui.evento("log", f"Navegador aberto ({self.nav.canal}).")
        return self.nav

    def agendar(self, funcao, *args):
        self.tarefas.put((funcao, args))


# ====================================================================== janela
class App:
    def __init__(self, root):
        self.root = root
        self.fila = queue.Queue()
        self.estado = motor.carregar_estado()
        self.mensagens = []
        self.plano = []
        self.ocupado = False

        root.title(f"Cobranças KAES {VERSAO}")
        root.geometry("1180x760")
        root.minsize(980, 620)
        root.configure(bg=CORES["fundo"])
        self._estilos()
        self._montar()

        self.trab = Trabalhador(self)
        self.trab.start()
        self.ia = None
        threading.Thread(target=self._iniciar_ia, daemon=True).start()

        self.root.after(100, self._processar_fila)
        self.root.protocol("WM_DELETE_WINDOW", self.fechar)
        if self.estado:
            self.mostrar_resultados(self.estado)
        if not base.carregar_config().get("clickup_url_lista"):
            self.root.after(600, self._primeira_configuracao)

    # ------------------------------------------------------------------ visual
    def _estilos(self):
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except tk.TclError:
            pass
        fonte = ("Segoe UI", 10)
        st.configure(".", font=fonte, background=CORES["fundo"], foreground=CORES["texto"])
        st.configure("Card.TFrame", background=CORES["card"])
        st.configure("Titulo.TLabel", font=("Segoe UI Semibold", 18), background=CORES["fundo"])
        st.configure("Sub.TLabel", foreground=CORES["suave"], background=CORES["fundo"])
        st.configure("Card.TLabel", background=CORES["card"])
        st.configure("Primario.TButton", font=("Segoe UI Semibold", 11), padding=(16, 10),
                     background=CORES["primaria"], foreground="white", borderwidth=0)
        st.map("Primario.TButton", background=[("active", CORES["primaria_hover"]), ("disabled", "#A5B4FC")])
        st.configure("Sec.TButton", padding=(12, 8))
        st.configure("Treeview", rowheight=28, font=fonte, background=CORES["card"], fieldbackground=CORES["card"])
        st.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))
        st.configure("TNotebook.Tab", padding=(14, 6), font=("Segoe UI", 10))

    def _montar(self):
        topo = ttk.Frame(self.root, padding=(18, 14, 18, 6))
        topo.pack(fill="x")
        ttk.Label(topo, text="Cobranças KAES", style="Titulo.TLabel").pack(side="left")
        self.lbl_ia = ttk.Label(topo, text="", style="Sub.TLabel")
        self.lbl_ia.pack(side="right")

        # caixa de comando
        cmd = ttk.Frame(self.root, padding=(18, 4, 18, 8))
        cmd.pack(fill="x")
        self.ent_cmd = ttk.Entry(cmd, font=("Segoe UI", 11))
        self.ent_cmd.pack(side="left", fill="x", expand=True, ipady=6)
        self.ent_cmd.insert(0, "Escreva um pedido, ex.: mensagem para Anderson, venceu 20/11/2026, sem juros")
        self.ent_cmd.bind("<FocusIn>", lambda e: self._limpar_dica())
        self.ent_cmd.bind("<Return>", lambda e: self.enviar_comando())
        ttk.Button(cmd, text="Enviar", style="Sec.TButton", command=self.enviar_comando).pack(side="left", padx=(8, 0))

        # botões principais
        bts = ttk.Frame(self.root, padding=(18, 4, 18, 10))
        bts.pack(fill="x")
        self.botoes = []
        for texto, acao in [("🔎  Conferir vencidos", self.cmd_conferir),
                            ("✉️  Gerar mensagens", self.cmd_mensagens),
                            ("✅  Atualizar ClickUp", self.cmd_atualizar),
                            ("👤  Mensagem p/ cliente", self.cmd_mensagem_cliente)]:
            b = ttk.Button(bts, text=texto, style="Primario.TButton", command=acao)
            b.pack(side="left", padx=(0, 10))
            self.botoes.append(b)
        ttk.Button(bts, text="⚙️ Configurações", style="Sec.TButton", command=lambda: self.abas.select(4)).pack(side="right")

        # abas
        self.abas = ttk.Notebook(self.root)
        self.abas.pack(fill="both", expand=True, padx=18)
        self._aba_resultados()
        self._aba_mensagens()
        self._aba_atualizar()
        self._aba_registro()
        self._aba_config()

        # rodapé com progresso
        rod = ttk.Frame(self.root, padding=(18, 8))
        rod.pack(fill="x")
        self.barra = ttk.Progressbar(rod, mode="determinate", length=260)
        self.barra.pack(side="left")
        self.lbl_status = ttk.Label(rod, text="Pronto.", style="Sub.TLabel")
        self.lbl_status.pack(side="left", padx=12)
        ttk.Button(rod, text="📁 Abrir pasta de relatórios", command=self.abrir_pasta).pack(side="right")

    def _tabela(self, pai, colunas, larguras):
        frame = ttk.Frame(pai)
        tv = ttk.Treeview(frame, columns=colunas, show="headings", selectmode="browse")
        for c, w in zip(colunas, larguras):
            tv.heading(c, text=c)
            tv.column(c, width=w, anchor="w", stretch=c in ("Cliente", "Observação"))
        sb = ttk.Scrollbar(frame, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for tag, cor in CORES.items():
            tv.tag_configure(tag, background=cor)
        return frame, tv

    def _aba_resultados(self):
        aba = ttk.Frame(self.abas, padding=10)
        self.abas.add(aba, text="  Resultados  ")
        topo = ttk.Frame(aba)
        topo.pack(fill="x", pady=(0, 8))
        self.lbl_resumo = ttk.Label(topo, text="Nenhuma conferência ainda. Clique em “Conferir vencidos”.")
        self.lbl_resumo.pack(side="left")
        ttk.Label(topo, text="Filtro:").pack(side="right", padx=(0, 4))
        self.filtro = ttk.Combobox(topo, state="readonly", width=20,
                                   values=["Todos"] + list(ROTULOS.values()))
        self.filtro.set("Todos")
        self.filtro.pack(side="right")
        self.filtro.bind("<<ComboboxSelected>>", lambda e: self.mostrar_resultados(self.estado))
        cols = ("Situação", "Cliente", "Status ClickUp", "Vencimento", "Asaas", "Valor", "Observação")
        frame, self.tv_res = self._tabela(aba, cols, (150, 300, 160, 95, 150, 110, 280))
        frame.pack(fill="both", expand=True)
        self.tv_res.bind("<Double-1>", self._abrir_item_resultado)
        ttk.Label(aba, text="Dica: dois cliques abre a fatura (ou a tarefa no ClickUp).",
                  style="Sub.TLabel").pack(anchor="w", pady=(6, 0))

    def _aba_mensagens(self):
        aba = ttk.Frame(self.abas, padding=10)
        self.abas.add(aba, text="  Mensagens  ")
        esq = ttk.Frame(aba)
        esq.pack(side="left", fill="y")
        ttk.Label(esq, text="Clientes").pack(anchor="w")
        self.lst_msg = tk.Listbox(esq, width=40, font=("Segoe UI", 10), activestyle="none",
                                  selectbackground=CORES["primaria"], relief="flat", highlightthickness=1)
        self.lst_msg.pack(fill="y", expand=True, pady=(4, 0))
        self.lst_msg.bind("<<ListboxSelect>>", self._mostrar_msg)
        dir_ = ttk.Frame(aba)
        dir_.pack(side="left", fill="both", expand=True, padx=(12, 0))
        self.txt_msg = tk.Text(dir_, wrap="word", font=("Segoe UI", 11), relief="flat",
                               highlightthickness=1, padx=12, pady=10)
        self.txt_msg.pack(fill="both", expand=True)
        b = ttk.Frame(dir_)
        b.pack(fill="x", pady=(8, 0))
        ttk.Button(b, text="📋 Copiar esta mensagem", style="Primario.TButton", command=self.copiar_msg).pack(side="left")
        ttk.Button(b, text="Copiar todas", style="Sec.TButton", command=self.copiar_todas).pack(side="left", padx=8)

    def _aba_atualizar(self):
        aba = ttk.Frame(self.abas, padding=10)
        self.abas.add(aba, text="  Atualizar ClickUp  ")
        ttk.Label(aba, text="Clique numa linha para marcar/desmarcar. Só os marcados (☑) serão alterados: "
                            "Status do Pagamento = PAGO e vencimento para o mesmo dia do mês seguinte.",
                  wraplength=1000).pack(anchor="w", pady=(0, 8))
        cols = ("✔", "Cliente", "Motivo", "Vencimento", "Novo vencimento", "Resultado")
        frame, self.tv_up = self._tabela(aba, cols, (40, 360, 120, 110, 130, 300))
        frame.pack(fill="both", expand=True)
        self.tv_up.bind("<ButtonRelease-1>", self._alternar_marcacao)
        b = ttk.Frame(aba)
        b.pack(fill="x", pady=(8, 0))
        self.bt_aplicar = ttk.Button(b, text="Aplicar marcados no ClickUp", style="Primario.TButton",
                                     command=self.aplicar_marcados)
        self.bt_aplicar.pack(side="left")
        self.botoes.append(self.bt_aplicar)

    def _aba_registro(self):
        aba = ttk.Frame(self.abas, padding=10)
        self.abas.add(aba, text="  Registro  ")
        self.txt_log = tk.Text(aba, wrap="word", font=("Consolas", 10), relief="flat", highlightthickness=1,
                               state="disabled", padx=8, pady=6)
        self.txt_log.pack(fill="both", expand=True)

    def _aba_config(self):
        aba = ttk.Frame(self.abas, padding=10)
        self.abas.add(aba, text="  Configurações  ")
        cv = tk.Canvas(aba, highlightthickness=0, bg=CORES["fundo"])
        sb = ttk.Scrollbar(aba, orient="vertical", command=cv.yview)
        f = ttk.Frame(cv)
        f.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0, 0), window=f, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        cfg = base.carregar_config()
        self.cfg_vars = {}

        def linha(rotulo, dica=""):
            ttk.Label(f, text=rotulo, font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(10, 0))
            if dica:
                ttk.Label(f, text=dica, style="Sub.TLabel", wraplength=1000).pack(anchor="w")

        linha("Link da lista no ClickUp (visualização “Visão Geral”)",
              "Abra a lista no ClickUp, clique na aba Visão Geral e copie o endereço do navegador.")
        self.cfg_vars["url"] = tk.StringVar(value=cfg.get("clickup_url_lista", ""))
        ttk.Entry(f, textvariable=self.cfg_vars["url"], width=110).pack(anchor="w", ipady=4)

        linha("Status a conferir (um por linha)")
        self.txt_status = tk.Text(f, height=4, width=60, font=("Segoe UI", 10))
        self.txt_status.insert("1.0", "\n".join(cfg.get("status_alvo", [])))
        self.txt_status.pack(anchor="w")

        linha("Mensagem padrão", "Use [NOME DO CLIENTE], [DATA DE VENCIMENTO] e [LINK DE COBRANÇA].")
        self.txt_modelo = tk.Text(f, height=12, width=110, font=("Segoe UI", 10), wrap="word")
        self.txt_modelo.insert("1.0", cfg.get("modelo_mensagem", ""))
        self.txt_modelo.pack(anchor="w")

        linha("Mensagem com vencimento alterado sem juros", "Também pode usar [NOVA DATA].")
        self.txt_modelo2 = tk.Text(f, height=12, width=110, font=("Segoe UI", 10), wrap="word")
        self.txt_modelo2.insert("1.0", cfg.get("modelo_mensagem_sem_juros", ""))
        self.txt_modelo2.pack(anchor="w")

        linha("Nomes no ClickUp → nomes no Asaas",
              'Para clientes que o programa não acha sozinho. Formato: "Nome no ClickUp": "Nome no Asaas",')
        self.txt_mapa = tk.Text(f, height=12, width=110, font=("Consolas", 10))
        self.txt_mapa.insert("1.0", base.texto_mapa())
        self.txt_mapa.pack(anchor="w")

        linha("Outras opções")
        op = ttk.Frame(f)
        op.pack(anchor="w")
        ttk.Label(op, text="Navegador:").pack(side="left")
        self.cfg_vars["nav"] = tk.StringVar(value=cfg.get("navegador", "msedge"))
        ttk.Combobox(op, textvariable=self.cfg_vars["nav"], values=["msedge", "chrome"], width=10,
                     state="readonly").pack(side="left", padx=(4, 20))
        self.cfg_vars["ia"] = tk.BooleanVar(value=cfg.get("usar_ia_local", True))
        ttk.Checkbutton(op, text="Usar IA local (Ollama), se estiver instalada",
                        variable=self.cfg_vars["ia"]).pack(side="left")

        ttk.Button(f, text="💾 Salvar configurações", style="Primario.TButton",
                   command=self.salvar_config).pack(anchor="w", pady=16)

    # ------------------------------------------------------------------ eventos (thread-safe)
    def evento(self, tipo, dado=None):
        self.fila.put((tipo, dado))

    def _processar_fila(self):
        try:
            while True:
                tipo, dado = self.fila.get_nowait()
                if tipo == "log":
                    self.log(dado)
                elif tipo == "status":
                    self.lbl_status.config(text=dado)
                elif tipo == "progresso":
                    atual, total, texto = dado
                    self.barra.config(maximum=max(total, 1), value=atual)
                    self.lbl_status.config(text=texto[:90])
                elif tipo == "ocupado":
                    self._set_ocupado(dado)
                elif tipo == "erro":
                    messagebox.showerror("Algo deu errado", f"{dado}\n\nVeja detalhes na aba Registro.")
                elif tipo == "chamar":
                    dado()
        except queue.Empty:
            pass
        self.root.after(100, self._processar_fila)

    def pedir_login_bloqueando(self, site):
        """Chamado pelo trabalhador: mostra o aviso na janela e espera o OK."""
        pronto = threading.Event()

        def mostrar():
            messagebox.showinfo(f"Login no {site}",
                                f"Faça login no {site} na janela do navegador que abriu.\n\n"
                                "Depois de entrar, clique em OK aqui.\n"
                                "(O login fica salvo; isso só acontece na primeira vez.)")
            pronto.set()

        self.evento("chamar", mostrar)
        pronto.wait()

    def _set_ocupado(self, sim):
        self.ocupado = sim
        for b in self.botoes:
            b.state(["disabled"] if sim else ["!disabled"])
        if not sim:
            self.barra.config(value=0)
            self.lbl_status.config(text="Pronto.")

    def log(self, texto):
        self.txt_log.config(state="normal")
        self.txt_log.insert("end", f"{motor.datetime.now():%H:%M:%S}  {texto}\n")
        self.txt_log.see("end")
        self.txt_log.config(state="disabled")
        self.lbl_status.config(text=str(texto)[:90])

    # ------------------------------------------------------------------ IA / comandos
    def _iniciar_ia(self):
        ia = IALocal(base.carregar_config())
        self.ia = ia
        self.evento("chamar", lambda: self.lbl_ia.config(
            text="Comandos: IA local ✓" if ia.ativa else "Comandos: palavras-chave (IA local desligada)"))

    def _limpar_dica(self):
        if self.ent_cmd.get().startswith("Escreva um pedido"):
            self.ent_cmd.delete(0, "end")

    def enviar_comando(self):
        texto = self.ent_cmd.get().strip()
        if not texto or texto.startswith("Escreva um pedido"):
            return
        self.ent_cmd.delete(0, "end")
        self.log(f"Pedido: {texto}")

        def interpretar():
            cmd = (self.ia or IALocal({"usar_ia_local": False})).interpretar(texto)
            self.evento("chamar", lambda: self._executar_comando(cmd))

        threading.Thread(target=interpretar, daemon=True).start()

    def _executar_comando(self, cmd):
        acao = cmd.get("acao")
        if acao == "conferir":
            self.cmd_conferir()
        elif acao == "mensagens":
            self.cmd_mensagens()
        elif acao == "atualizar":
            self.cmd_atualizar()
        elif acao == "mensagem_cliente":
            self.cmd_mensagem_cliente(cmd.get("cliente"), cmd.get("data_original"), cmd.get("sem_juros"))
        elif acao == "ajuda":
            self.abas.select(3)
            self.log("Botões: Conferir → Gerar mensagens → Atualizar ClickUp. "
                     "Ou peça: 'mensagem para <cliente>, venceu dd/mm/aaaa, sem juros'.")
        elif acao == "sair":
            self.fechar()
        else:
            messagebox.showinfo("Não entendi", "Não entendi o pedido. Use os botões ou tente escrever de outro jeito.")

    def _pode(self):
        if self.ocupado:
            messagebox.showinfo("Aguarde", "Ainda estou trabalhando no pedido anterior.")
            return False
        if not base.carregar_config().get("clickup_url_lista"):
            self._primeira_configuracao()
            return False
        return True

    # ------------------------------------------------------------------ 1 conferir
    def cmd_conferir(self):
        if not self._pode():
            return
        self.abas.select(3)

        def tarefa():
            nav = self.trab.navegador()
            estado = motor.conferir(nav, avisar=lambda t: self.evento("log", t),
                                    progresso=lambda a, t, x: self.evento("progresso", (a, t, x)))
            self.evento("chamar", lambda: self._pos_conferir(estado))

        self.trab.agendar(tarefa)

    def _pos_conferir(self, estado):
        self.estado = estado
        self.mostrar_resultados(estado)
        self.abas.select(0)

    def mostrar_resultados(self, estado):
        tv = self.tv_res
        tv.delete(*tv.get_children())
        if not estado:
            return
        filtro = self.filtro.get()
        contagem = {}
        for i, r in enumerate(estado["resultados"]):
            cl = r["classificacao"] if r["classificacao"] in ROTULOS else "outro"
            contagem[cl] = contagem.get(cl, 0) + 1
            if filtro != "Todos" and ROTULOS[cl] != filtro:
                continue
            sit = "; ".join(c["situacao"] for c in r["cobrancas"]) or "—"
            val = "; ".join(c["valor"] for c in r["cobrancas"]) or "—"
            obs = motor.MOTIVOS.get(r["busca"], "") if cl == "nao_encontrado" else (
                "CONFIRMAR: nome aproximado" if r.get("confirmar_nome") else "")
            tv.insert("", "end", iid=f"r{i}", tags=(cl,),
                      values=(ROTULOS[cl], r["nome"], r["status_clickup"], r["vencimento"], sit, val, obs))
        for i, p in enumerate(estado["porcentagem"]):
            contagem["porcentagem"] = contagem.get("porcentagem", 0) + 1
            if filtro not in ("Todos", ROTULOS["porcentagem"]):
                continue
            tv.insert("", "end", iid=f"p{i}", tags=("porcentagem",),
                      values=(ROTULOS["porcentagem"], p["nome"], p.get("status_clickup", ""), p["vencimento"],
                              "não conferido", "—", "Porcentagem = SIM"))
        partes = [f"{ROTULOS[k]}: {v}" for k, v in contagem.items()]
        extra = f"   |   Sem data: {', '.join(estado['sem_data'])}" if estado.get("sem_data") else ""
        self.lbl_resumo.config(text=f"Conferência de {estado['data']}   —   " + "   ".join(partes) + extra)

    def _abrir_item_resultado(self, _e):
        sel = self.tv_res.selection()
        if not sel or not self.estado:
            return
        iid = sel[0]
        if iid.startswith("r"):
            r = self.estado["resultados"][int(iid[1:])]
            link = next((c["link"] for c in r["cobrancas"] if c.get("link")), "") or r["url"]
        else:
            link = self.estado["porcentagem"][int(iid[1:])]["url"]
        webbrowser.open(link)

    # ------------------------------------------------------------------ 2 mensagens
    def _estado_ok(self):
        if not self.estado:
            messagebox.showinfo("Falta a conferência", "Clique primeiro em “Conferir vencidos”.")
            return False
        if self.estado["data"] != R.data_br(R.hoje()):
            return messagebox.askyesno("Conferência antiga",
                                       f"A última conferência é de {self.estado['data']}. Usar mesmo assim?")
        return True

    def cmd_mensagens(self):
        if not self._estado_ok():
            return
        self.mensagens = motor.mensagens_inadimplentes(self.estado)
        if not self.mensagens:
            messagebox.showinfo("Mensagens", "Nenhum inadimplente na última conferência. 🎉")
            return
        motor.salvar_texto("\n\n".join(f"----- {n} -----\n{m}" for n, m in self.mensagens), "mensagens")
        self._carregar_lista_msgs()

    def _carregar_lista_msgs(self):
        self.lst_msg.delete(0, "end")
        for nome, _ in self.mensagens:
            self.lst_msg.insert("end", nome)
        self.abas.select(1)
        self.lst_msg.selection_clear(0, "end")
        self.lst_msg.selection_set(0)
        self._mostrar_msg()

    def _mostrar_msg(self, _e=None):
        sel = self.lst_msg.curselection()
        if not sel:
            return
        self.txt_msg.delete("1.0", "end")
        self.txt_msg.insert("1.0", self.mensagens[sel[0]][1])

    def copiar_msg(self):
        texto = self.txt_msg.get("1.0", "end").strip()
        if texto:
            self.root.clipboard_clear()
            self.root.clipboard_append(texto)
            self.lbl_status.config(text="Mensagem copiada! É só colar no WhatsApp.")

    def copiar_todas(self):
        if self.mensagens:
            self.root.clipboard_clear()
            self.root.clipboard_append("\n\n".join(m for _, m in self.mensagens))
            self.lbl_status.config(text=f"{len(self.mensagens)} mensagens copiadas.")

    # ------------------------------------------------------------------ 3 atualizar
    def cmd_atualizar(self):
        if not self._estado_ok():
            return
        self.plano = motor.plano_atualizacao(self.estado)
        tv = self.tv_up
        tv.delete(*tv.get_children())
        if not self.plano:
            messagebox.showinfo("Atualizar", "Nada para atualizar (ou já foi atualizado hoje).")
            return
        for i, it in enumerate(self.plano):
            tv.insert("", "end", iid=str(i), tags=("pago" if it["motivo"] == "pago" else "porcentagem",),
                      values=("☑", it["nome"], it["motivo"], it["vencimento"], it["nova_data"], ""))
        self.abas.select(2)

    def _alternar_marcacao(self, e):
        iid = self.tv_up.identify_row(e.y)
        if not iid or self.ocupado:
            return
        v = list(self.tv_up.item(iid, "values"))
        if v[5].startswith("✓"):
            return
        v[0] = "☐" if v[0] == "☑" else "☑"
        self.tv_up.item(iid, values=v)

    def aplicar_marcados(self):
        if self.ocupado or not self.plano:
            return
        marcados = [self.plano[int(i)] for i in self.tv_up.get_children()
                    if self.tv_up.item(i, "values")[0] == "☑" and not self.tv_up.item(i, "values")[5].startswith("✓")]
        if not marcados:
            messagebox.showinfo("Atualizar", "Nenhuma linha marcada.")
            return
        if not messagebox.askyesno("Confirmar", f"Alterar {len(marcados)} tarefa(s) no ClickUp?\n\n"
                                                "Status do Pagamento = PAGO e vencimento +1 mês."):
            return

        def resultado(item, problemas):
            iid = str(self.plano.index(item))

            def ui():
                v = list(self.tv_up.item(iid, "values"))
                v[5] = "✓ feito" if not problemas else "✗ " + "; ".join(problemas)
                self.tv_up.item(iid, values=v)

            self.evento("chamar", ui)
            self.evento("log", f"{item['nome']}: {'ok' if not problemas else '; '.join(problemas)}")

        def tarefa():
            nav = self.trab.navegador()
            for n, item in enumerate(marcados, 1):
                self.evento("progresso", (n, len(marcados), f"Atualizando {item['nome']}"))
                motor.aplicar(nav, self.estado, [item], ao_terminar_item=resultado)

        self.trab.agendar(tarefa)

    # ------------------------------------------------------------------ 4 mensagem para cliente
    def cmd_mensagem_cliente(self, cliente=None, data_original=None, sem_juros=False):
        if self.ocupado:
            messagebox.showinfo("Aguarde", "Ainda estou trabalhando no pedido anterior.")
            return
        dlg = DialogoCliente(self.root, cliente or "", data_original or "", bool(sem_juros))
        if not dlg.resultado:
            return
        cliente, sem_juros, data_original = dlg.resultado

        def buscar():
            nav = self.trab.navegador()
            linhas = motor.buscar_cobrancas_cliente(nav, cliente)
            self.evento("chamar", lambda: self._escolher_cobranca(cliente, linhas, data_original, sem_juros))

        self.trab.agendar(buscar)

    def _escolher_cobranca(self, cliente, linhas, data_original, sem_juros):
        if not linhas:
            messagebox.showwarning("Não encontrado", f"Não encontrei cobranças para “{cliente}” no Asaas.")
            return
        dlg = DialogoEscolha(self.root, cliente, linhas)
        if dlg.escolha is None:
            return
        linha = linhas[dlg.escolha]

        def gerar():
            nav = self.trab.navegador()
            situacao, msg = motor.mensagem_da_cobranca(nav, cliente, linha, data_original, sem_juros)
            self.evento("log", f"Cobrança de {cliente}: {situacao}")

            def ui():
                self.mensagens = [(f"{cliente} — {R.data_br(linha['vencimento'])}", msg)] + self.mensagens
                self._carregar_lista_msgs()

            self.evento("chamar", ui)

        self.trab.agendar(gerar)

    # ------------------------------------------------------------------ config / outros
    def salvar_config(self):
        try:
            base.salvar_texto_mapa(self.txt_mapa.get("1.0", "end").strip() or "{}")
        except Exception as e:
            messagebox.showerror("Erro no quadro de nomes",
                                 f"O quadro “Nomes no ClickUp → Asaas” tem um erro de formato:\n{e}\n\n"
                                 'Cada linha deve ser assim: "Nome no ClickUp": "Nome no Asaas",\n'
                                 "(a última linha sem vírgula no final)")
            return
        cfg = base.carregar_config()
        cfg["clickup_url_lista"] = self.cfg_vars["url"].get().strip()
        cfg["status_alvo"] = [s.strip() for s in self.txt_status.get("1.0", "end").splitlines() if s.strip()]
        cfg["modelo_mensagem"] = self.txt_modelo.get("1.0", "end").strip()
        cfg["modelo_mensagem_sem_juros"] = self.txt_modelo2.get("1.0", "end").strip()
        cfg["navegador"] = self.cfg_vars["nav"].get()
        cfg["usar_ia_local"] = bool(self.cfg_vars["ia"].get())
        base.salvar_config(cfg)
        self.lbl_status.config(text="Configurações salvas.")
        messagebox.showinfo("Configurações", "Salvo!")

    def _primeira_configuracao(self):
        url = simpledialog.askstring(
            "Primeira configuração",
            "Cole o link da lista no ClickUp (aba “Visão Geral” da lista Gestão de Contratos & Cobranças):",
            parent=self.root)
        if url and "clickup.com" in url:
            cfg = base.carregar_config()
            cfg["clickup_url_lista"] = url.strip()
            base.salvar_config(cfg)
            self.cfg_vars["url"].set(url.strip())
            self.lbl_status.config(text="Link do ClickUp salvo.")

    def abrir_pasta(self):
        base.PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(base.PASTA_RELATORIOS)
        else:
            webbrowser.open(str(base.PASTA_RELATORIOS))

    def fechar(self):
        if self.ocupado and not messagebox.askyesno("Sair", "Ainda estou trabalhando. Sair mesmo assim?"):
            return
        self.trab.tarefas.put((None, None))
        self.root.after(300, self.root.destroy)


# ====================================================================== diálogos
class DialogoCliente(simpledialog.Dialog):
    def __init__(self, pai, cliente, data_original, sem_juros):
        self._ini = (cliente, data_original, sem_juros)
        self.resultado = None
        super().__init__(pai, "Mensagem para um cliente")

    def body(self, f):
        ttk.Label(f, text="Nome do cliente (como no ClickUp ou no Asaas):").grid(row=0, column=0, sticky="w")
        self.e_cli = ttk.Entry(f, width=45)
        self.e_cli.insert(0, self._ini[0])
        self.e_cli.grid(row=1, column=0, sticky="we", pady=(2, 10))
        self.v_sj = tk.BooleanVar(value=self._ini[2])
        ttk.Checkbutton(f, text="O vencimento foi alterado sem juros", variable=self.v_sj).grid(row=2, column=0, sticky="w")
        ttk.Label(f, text="Data original do vencimento (dd/mm/aaaa):").grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.e_data = ttk.Entry(f, width=15)
        self.e_data.insert(0, self._ini[1])
        self.e_data.grid(row=4, column=0, sticky="w")
        return self.e_cli

    def validate(self):
        if not self.e_cli.get().strip():
            messagebox.showwarning("Falta o nome", "Escreva o nome do cliente.", parent=self)
            return False
        if self.v_sj.get() and not R.ler_data(self.e_data.get()):
            messagebox.showwarning("Falta a data", "Informe a data original (dd/mm/aaaa).", parent=self)
            return False
        return True

    def apply(self):
        d = R.ler_data(self.e_data.get())
        self.resultado = (self.e_cli.get().strip(), self.v_sj.get(), R.data_br(d) if d else None)


class DialogoEscolha(simpledialog.Dialog):
    def __init__(self, pai, cliente, linhas):
        self.linhas, self.escolha = linhas, None
        super().__init__(pai, f"Cobranças de {cliente}")

    def body(self, f):
        ttk.Label(f, text="Escolha a cobrança para a mensagem:").pack(anchor="w")
        self.tv = ttk.Treeview(f, columns=("Venc.", "Valor", "Cliente no Asaas", "Situação"), show="headings",
                               height=min(12, len(self.linhas)))
        for c, w in zip(("Venc.", "Valor", "Cliente no Asaas", "Situação"), (95, 110, 320, 150)):
            self.tv.heading(c, text=c)
            self.tv.column(c, width=w)
        for i, l in enumerate(self.linhas[:30]):
            self.tv.insert("", "end", iid=str(i), values=(R.data_br(l["vencimento"]) if l["vencimento"] else "?",
                                                          l["valor"], l["cliente"], l.get("dica", "")))
        self.tv.pack(fill="both", expand=True, pady=6)
        primeira_vencida = next((i for i, l in enumerate(self.linhas[:30]) if l.get("dica") == "vencida"), 0)
        self.tv.selection_set(str(primeira_vencida))
        self.tv.bind("<Double-1>", lambda e: self.ok())
        return self.tv

    def apply(self):
        sel = self.tv.selection()
        self.escolha = int(sel[0]) if sel else None


# ====================================================================== autoteste (usado no build)
def autoteste():
    """Abre a janela, abre o Edge escondido e fecha. Usado pelo GitHub para provar que o .exe funciona."""
    import tempfile
    log = base.DADOS / "autoteste.log"
    resultado = {"janela": False, "navegador": False, "erro": ""}
    root = tk.Tk()
    try:
        App(root)
        root.update()
        resultado["janela"] = True
        from navegador import Navegador
        nav = Navegador({"navegador": "msedge"}, perfil=tempfile.mkdtemp(), headless=True)
        nav.page.goto("about:blank")
        resultado["navegador"] = nav.canal
        nav.fechar()
    except Exception:
        resultado["erro"] = traceback.format_exc()
    finally:
        log.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            root.destroy()
        except Exception:
            pass
    print(json.dumps(resultado, ensure_ascii=False))
    sys.exit(0 if resultado["janela"] and resultado["navegador"] else 1)


def main():
    if "--autoteste" in sys.argv:
        autoteste()
    root = tk.Tk()
    try:
        root.iconbitmap(default=str(base.PASTA_PADROES / "icone.ico"))
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
