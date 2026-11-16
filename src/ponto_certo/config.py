"""Configuração da automação.

Tudo o que é credencial vem de variável de ambiente (ou do arquivo .env, que
fica fora do Git). Nenhum segredo é escrito no código.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from zoneinfo import ZoneInfo

RAIZ = Path(__file__).resolve().parents[2]
FUSO = ZoneInfo("America/Sao_Paulo")


class ErroConfiguracao(Exception):
    """Configuração ausente ou inválida: a execução não pode começar."""


@dataclass(frozen=True)
class Config:
    modo: str = "simulado"  # "simulado" ou "real"
    token: str = ""
    base_url: str = "https://api.olhovivo.sptrans.com.br/v2.1"
    arquivo_linhas: Path = RAIZ / "config" / "linhas_monitoradas.csv"
    arquivo_cenario: Path = RAIZ / "simulacao" / "cenario_padrao.json"
    dir_saida: Path = RAIZ / "saida"
    dir_logs: Path = RAIZ / "logs"
    # Regras de negócio (razão = minutos observados / intervalo programado)
    limite_atencao: float = 1.2
    limite_critico: float = 2.0
    execucoes_para_alerta: int = 2
    # Resiliência
    timeout_s: float = 10.0
    tentativas: int = 3
    espera_base_s: float = 1.0

    @property
    def banco(self) -> Path:
        return self.dir_saida / "ponto_certo.db"

    @property
    def painel_json(self) -> Path:
        return self.dir_saida / "painel_linhas.json"


def _ler_dotenv(caminho: Path) -> dict[str, str]:
    """Lê um .env simples (CHAVE=valor). Variáveis de ambiente reais têm prioridade."""
    valores: dict[str, str] = {}
    if not caminho.is_file():
        return valores
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def carregar_config(**sobrescritas) -> Config:
    env = {**_ler_dotenv(RAIZ / ".env"), **os.environ}
    cfg = Config(
        modo=env.get("PONTO_CERTO_MODO", "simulado").lower(),
        token=env.get("OLHO_VIVO_TOKEN", ""),
        base_url=env.get("OLHO_VIVO_BASE_URL", Config.base_url).rstrip("/"),
    )
    sobrescritas = {k: v for k, v in sobrescritas.items() if v is not None}
    cfg = replace(cfg, **sobrescritas)
    if cfg.modo not in ("simulado", "real"):
        raise ErroConfiguracao(f"Modo desconhecido: {cfg.modo!r} (use 'simulado' ou 'real')")
    return cfg
