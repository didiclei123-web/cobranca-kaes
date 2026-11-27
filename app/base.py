"""Pastas e configurações. Tudo fica ao lado do .exe (portátil)."""
import json
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    PASTA = Path(sys.executable).parent          # pasta do CobrancasKAES.exe
    PASTA_PADROES = Path(getattr(sys, "_MEIPASS", PASTA))
else:
    PASTA = Path(__file__).parent
    PASTA_PADROES = PASTA

DADOS = PASTA / "dados"                          # login, relatórios, configurações
DADOS.mkdir(exist_ok=True)
ARQ_CONFIG = DADOS / "config.json"
ARQ_MAPA = DADOS / "mapa_asaas.json"
ARQ_ESTADO = DADOS / "ultima_conferencia.json"
PASTA_RELATORIOS = DADOS / "relatorios"
PASTA_PERFIL = DADOS / "perfil_navegador"


def _ler(caminho: Path, padrao):
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:
        return padrao


def _primeira_vez(destino: Path, nome_padrao: str):
    if not destino.exists():
        origem = PASTA_PADROES / nome_padrao
        if origem.exists():
            destino.write_text(origem.read_text(encoding="utf-8"), encoding="utf-8")


_primeira_vez(ARQ_CONFIG, "config.json")
_primeira_vez(ARQ_MAPA, "mapa_asaas.json")


def carregar_config() -> dict:
    return _ler(ARQ_CONFIG, {})


def salvar_config(cfg: dict):
    ARQ_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def carregar_mapa() -> dict:
    return {k: v for k, v in _ler(ARQ_MAPA, {}).items() if not k.startswith("_")}


def texto_mapa() -> str:
    return ARQ_MAPA.read_text(encoding="utf-8") if ARQ_MAPA.exists() else "{}"


def salvar_texto_mapa(texto: str):
    json.loads(texto)  # valida antes de salvar (gera erro se estiver mal escrito)
    ARQ_MAPA.write_text(texto, encoding="utf-8")
