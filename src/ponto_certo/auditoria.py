"""Log de auditoria em JSON Lines: um evento por linha, com data/hora e execução.

Arquivo: logs/auditoria-AAAA-MM-DD.jsonl. Campos cujo nome sugere segredo
(token, senha, cookie...) são mascarados antes de gravar.
"""
from __future__ import annotations

import json
from pathlib import Path

SENSIVEIS = ("token", "senha", "password", "secret", "cookie", "authorization")


def _mascarar(dados: dict) -> dict:
    return {k: ("***" if any(s in k.lower() for s in SENSIVEIS) else v) for k, v in dados.items()}


class Auditoria:
    def __init__(self, dir_logs: Path, execucao_id: str, agora, eco: bool = True):
        self._dir = dir_logs
        self._execucao_id = execucao_id
        self._agora = agora
        self._eco = eco
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def arquivo(self) -> Path:
        return self._dir / f"auditoria-{self._agora():%Y-%m-%d}.jsonl"

    def registrar(self, nivel: str, evento: str, **dados) -> None:
        momento = self._agora()
        registro = {"ts": momento.isoformat(timespec="seconds"), "execucao_id": self._execucao_id,
                    "nivel": nivel, "evento": evento, **_mascarar(dados)}
        with self.arquivo.open("a", encoding="utf-8") as arq:
            arq.write(json.dumps(registro, ensure_ascii=False) + "\n")
        if self._eco:
            detalhes = " ".join(f"{k}={v}" for k, v in registro.items()
                                if k not in ("ts", "execucao_id", "nivel", "evento"))
            print(f"{momento:%H:%M:%S} [{nivel:<5}] {evento} {detalhes}".rstrip())

    def info(self, evento: str, **dados) -> None:
        self.registrar("INFO", evento, **dados)

    def aviso(self, evento: str, **dados) -> None:
        self.registrar("AVISO", evento, **dados)

    def erro(self, evento: str, **dados) -> None:
        self.registrar("ERRO", evento, **dados)
