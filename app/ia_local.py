"""
IA local opcional (Ollama). Se o Ollama não estiver instalado/aberto,
o programa usa automaticamente o entendimento por palavras-chave.
"""
import json
import urllib.request

from regras import ACOES, interpretar_palavras_chave

INSTRUCAO = """Você converte pedidos em português para um comando JSON de um programa de cobranças.
Ações possíveis:
- "conferir": verificar quem está vencido no ClickUp e se pagou no Asaas
- "mensagens": gerar mensagens de cobrança para TODOS os inadimplentes da última conferência
- "atualizar": marcar como PAGO e empurrar o vencimento dos pagos/porcentagem no ClickUp
- "mensagem_cliente": gerar mensagem de cobrança para UM cliente específico
- "ajuda": explicar o que o programa faz
- "sair": encerrar
Responda SOMENTE com JSON no formato:
{"acao": "...", "cliente": "nome ou null", "data_original": "dd/mm/aaaa ou null", "sem_juros": true/false}
"data_original" é a data em que a fatura venceu originalmente, se o pedido disser.
"sem_juros" é true se o pedido disser que o vencimento foi alterado/prorrogado sem juros."""


class IALocal:
    def __init__(self, cfg: dict):
        self.url = cfg.get("ollama_url", "http://localhost:11434")
        self.modelo = cfg.get("ollama_modelo", "llama3.2:3b")
        self.ativa = bool(cfg.get("usar_ia_local", True)) and self._disponivel()

    def _disponivel(self) -> bool:
        try:
            with urllib.request.urlopen(self.url + "/api/tags", timeout=2) as r:
                modelos = [m.get("name", "") for m in json.load(r).get("models", [])]
            return any(m.startswith(self.modelo.split(":")[0]) for m in modelos)
        except Exception:
            return False

    def interpretar(self, texto: str) -> dict:
        base = interpretar_palavras_chave(texto)
        if base["acao"] in ("sair", "ajuda") or texto.strip().isdigit() or not self.ativa:
            return base
        try:
            corpo = json.dumps({
                "model": self.modelo, "stream": False, "format": "json",
                "messages": [{"role": "system", "content": INSTRUCAO},
                             {"role": "user", "content": texto}],
                "options": {"temperature": 0},
            }).encode()
            req = urllib.request.Request(self.url + "/api/chat", data=corpo,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                resposta = json.loads(json.load(r)["message"]["content"])
            if resposta.get("acao") not in ACOES:
                return base
            for k in ("cliente", "data_original"):
                if resposta.get(k) in ("null", "", None):
                    resposta[k] = None
            resposta["sem_juros"] = bool(resposta.get("sem_juros"))
            return resposta
        except Exception:
            return base
