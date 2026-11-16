"""Regras de negócio: interpretar a previsão e classificar a situação da linha.

Indicador = o maior entre (a) a espera até o próximo ônibus e (b) o intervalo
entre o primeiro e o segundo ônibus previstos. Razão = indicador / intervalo
programado.

    sem ônibus previsto        -> SEM_PREVISAO (tratado como crítico)
    razão <= limite_atencao    -> NORMAL
    razão <= limite_critico    -> ATENCAO
    razão >  limite_critico    -> CRITICO
"""
from __future__ import annotations

from dataclasses import dataclass

from .olho_vivo import ErroRespostaInvalida

NORMAL, ATENCAO, CRITICO = "NORMAL", "ATENCAO", "CRITICO"
SEM_PREVISAO, FALHA_COLETA = "SEM_PREVISAO", "FALHA_COLETA"
CRITICAS = (CRITICO, SEM_PREVISAO)


@dataclass(frozen=True)
class Avaliacao:
    classificacao: str
    espera_min: int | None
    intervalo_observado_min: int | None
    indicador_min: int | None
    razao: float | None


def _minutos(hhmm: str) -> int:
    partes = str(hhmm).split(":")
    if len(partes) != 2 or not all(p.isdigit() for p in partes):
        raise ErroRespostaInvalida(f"horário fora do formato HH:MM: {hhmm!r}")
    h, m = int(partes[0]), int(partes[1])
    if h > 23 or m > 59:
        raise ErroRespostaInvalida(f"horário inexistente: {hhmm!r}")
    return h * 60 + m


def interpretar_previsao(resposta, codigo_linha: int) -> list[int]:
    """Converte a resposta de /Previsao em minutos até cada chegada (ordem crescente)."""
    if not isinstance(resposta, dict) or "hr" not in resposta:
        raise ErroRespostaInvalida("resposta sem o campo 'hr'")
    agora = _minutos(resposta["hr"])
    parada = resposta.get("p")
    if parada is None:
        return []  # a API devolve p = null quando não há previsão para a parada
    if not isinstance(parada, dict) or not isinstance(parada.get("l", []), list):
        raise ErroRespostaInvalida("campo 'p' fora do formato esperado")

    chegadas: list[int] = []
    for linha in parada.get("l", []):
        if not isinstance(linha, dict):
            raise ErroRespostaInvalida("item de linha fora do formato esperado")
        if linha.get("cl") not in (None, codigo_linha):
            continue
        for veiculo in linha.get("vs") or []:
            if not isinstance(veiculo, dict) or "t" not in veiculo:
                raise ErroRespostaInvalida("veículo sem horário previsto ('t')")
            diferenca = (_minutos(veiculo["t"]) - agora) % 1440  # cobre a virada da meia-noite
            # Previsão levemente atrasada em relação ao relógio da API = ônibus chegando.
            chegadas.append(0 if diferenca > 1200 else diferenca)
    return sorted(chegadas)


def classificar(chegadas_min: list[int], intervalo_programado_min: float,
                limite_atencao: float = 1.2, limite_critico: float = 2.0) -> Avaliacao:
    if not chegadas_min:
        return Avaliacao(SEM_PREVISAO, None, None, None, None)

    espera = chegadas_min[0]
    intervalo = chegadas_min[1] - chegadas_min[0] if len(chegadas_min) > 1 else None
    indicador = max(espera, intervalo or 0)
    razao = round(indicador / intervalo_programado_min, 2)

    if razao <= limite_atencao:
        classe = NORMAL
    elif razao <= limite_critico:
        classe = ATENCAO
    else:
        classe = CRITICO
    return Avaliacao(classe, espera, intervalo, indicador, razao)
