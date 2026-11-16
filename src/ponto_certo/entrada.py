"""Leitura e validação da lista de linhas monitoradas (entrada do processo)."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .config import ErroConfiguracao

CAMPOS = ["linha", "codigo_linha", "codigo_parada", "nome_parada", "intervalo_programado_min"]


@dataclass(frozen=True)
class LinhaMonitorada:
    linha: str  # letreiro, ex.: 8000-10
    codigo_linha: int  # código interno da linha no Olho Vivo (campo "cl")
    codigo_parada: int  # código da parada de referência (campo "cp")
    nome_parada: str
    intervalo_programado_min: float


@dataclass(frozen=True)
class Rejeicao:
    numero_linha_csv: int
    conteudo: str
    motivo: str


def carregar_linhas(caminho: Path) -> tuple[list[LinhaMonitorada], list[Rejeicao]]:
    """Devolve (linhas válidas, registros rejeitados com o motivo).

    Um registro ruim não derruba a execução: ele é rejeitado e auditado.
    Arquivo ausente, sem cabeçalho ou sem nenhuma linha válida impede a execução.
    """
    if not caminho.is_file():
        raise ErroConfiguracao(f"Arquivo de linhas não encontrado: {caminho}")

    validas: list[LinhaMonitorada] = []
    rejeitadas: list[Rejeicao] = []
    vistos: set[tuple[int, int]] = set()

    with caminho.open(encoding="utf-8-sig", newline="") as arq:
        leitor = csv.DictReader(arq)
        faltando = [c for c in CAMPOS if c not in (leitor.fieldnames or [])]
        if faltando:
            raise ErroConfiguracao(f"Colunas ausentes em {caminho.name}: {', '.join(faltando)}")

        for registro in leitor:
            n = leitor.line_num
            bruto = ";".join((registro.get(c) or "").strip() for c in CAMPOS)
            try:
                item = _converter(registro)
            except ValueError as erro:
                rejeitadas.append(Rejeicao(n, bruto, str(erro)))
                continue
            chave = (item.codigo_linha, item.codigo_parada)
            if chave in vistos:
                rejeitadas.append(Rejeicao(n, bruto, "duplicado: linha e parada já cadastradas"))
                continue
            vistos.add(chave)
            validas.append(item)

    if not validas:
        raise ErroConfiguracao(f"Nenhuma linha válida em {caminho.name}")
    return validas, rejeitadas


def _converter(registro: dict) -> LinhaMonitorada:
    def texto(campo: str) -> str:
        valor = (registro.get(campo) or "").strip()
        if not valor:
            raise ValueError(f"campo obrigatório vazio: {campo}")
        return valor

    def inteiro(campo: str) -> int:
        valor = texto(campo)
        if not valor.isdigit() or int(valor) <= 0:
            raise ValueError(f"{campo} deve ser inteiro positivo (recebido: {valor!r})")
        return int(valor)

    intervalo_txt = texto("intervalo_programado_min").replace(",", ".")
    try:
        intervalo = float(intervalo_txt)
    except ValueError:
        raise ValueError(f"intervalo_programado_min não numérico (recebido: {intervalo_txt!r})") from None
    if not 1 <= intervalo <= 180:
        raise ValueError(f"intervalo_programado_min fora da faixa 1 a 180 (recebido: {intervalo_txt})")

    return LinhaMonitorada(
        linha=texto("linha"),
        codigo_linha=inteiro("codigo_linha"),
        codigo_parada=inteiro("codigo_parada"),
        nome_parada=texto("nome_parada"),
        intervalo_programado_min=intervalo,
    )
