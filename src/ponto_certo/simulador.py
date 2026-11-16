"""Cliente simulado: devolve respostas no MESMO formato da API Olho Vivo.

Existe para que a automação possa ser demonstrada e testada sem token e sem
depender do que está acontecendo na rua naquele minuto. O comportamento de cada
linha é declarado em simulacao/cenario_padrao.json, então a simulação é
reproduzível e auditável (nada de números aleatórios).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .config import ErroConfiguracao
from .olho_vivo import ErroApiIndisponivel

PADRAO = {"chegadas_min": [4, 12]}


class ClienteSimulado:
    fonte = "simulado"

    def __init__(self, cenario: dict, agora):
        self._cenario = cenario
        self._agora = agora

    @classmethod
    def de_arquivo(cls, caminho: Path, agora) -> "ClienteSimulado":
        if not caminho.is_file():
            raise ErroConfiguracao(f"Cenário de simulação não encontrado: {caminho}")
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except ValueError:
            raise ErroConfiguracao(f"Cenário de simulação não é um JSON válido: {caminho.name}") from None
        return cls(dados.get("linhas", {}), agora)

    def autenticar(self) -> None:
        return None

    def previsao(self, codigo_parada: int, codigo_linha: int):
        regra = self._cenario.get(str(codigo_linha), PADRAO)
        erro = regra.get("erro")
        if erro == "indisponivel":
            raise ErroApiIndisponivel("/Previsao: sem resposta após 3 tentativas (simulado)")
        if erro == "resposta_invalida":
            return {"mensagem": "formato inesperado"}

        momento: datetime = self._agora()
        chegadas = regra.get("chegadas_min", [])
        if not chegadas:
            return {"hr": momento.strftime("%H:%M"), "p": None}
        veiculos = [
            {"p": f"SIM{i + 1:02d}", "t": (momento + timedelta(minutes=m)).strftime("%H:%M"), "a": True}
            for i, m in enumerate(chegadas)
        ]
        return {
            "hr": momento.strftime("%H:%M"),
            "p": {"cp": codigo_parada, "np": "PARADA SIMULADA",
                  "l": [{"cl": codigo_linha, "qv": len(veiculos), "vs": veiculos}]},
        }
