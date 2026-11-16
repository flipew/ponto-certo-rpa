"""Persistência e entrega ao MVP: banco SQLite + arquivo JSON do painel."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from .regras import CRITICAS

ESQUEMA = """
CREATE TABLE IF NOT EXISTS execucoes (
    id TEXT PRIMARY KEY, inicio TEXT NOT NULL, fim TEXT, modo TEXT NOT NULL, fonte TEXT,
    status TEXT NOT NULL, linhas_lidas INTEGER DEFAULT 0, rejeitadas INTEGER DEFAULT 0,
    processadas INTEGER DEFAULT 0, falhas INTEGER DEFAULT 0, alertas INTEGER DEFAULT 0,
    codigo_saida INTEGER
);
CREATE TABLE IF NOT EXISTS medicoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, execucao_id TEXT NOT NULL REFERENCES execucoes(id),
    coletado_em TEXT NOT NULL, linha TEXT NOT NULL, codigo_linha INTEGER NOT NULL,
    codigo_parada INTEGER NOT NULL, nome_parada TEXT, intervalo_programado_min REAL,
    espera_min INTEGER, intervalo_observado_min INTEGER, indicador_min INTEGER, razao REAL,
    classificacao TEXT NOT NULL, detalhe TEXT
);
CREATE INDEX IF NOT EXISTS ix_medicoes_linha ON medicoes (codigo_linha, codigo_parada, id);
CREATE TABLE IF NOT EXISTS alertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT, criado_em TEXT NOT NULL, data_ref TEXT NOT NULL,
    execucao_id TEXT NOT NULL, linha TEXT NOT NULL, codigo_linha INTEGER NOT NULL,
    codigo_parada INTEGER NOT NULL, nome_parada TEXT, tipo TEXT NOT NULL,
    mensagem TEXT NOT NULL, reclamacao TEXT NOT NULL,
    UNIQUE (data_ref, codigo_linha, codigo_parada)
);
"""


class Armazenamento:
    def __init__(self, caminho: Path):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(caminho)
        self._con.row_factory = sqlite3.Row
        self._con.executescript(ESQUEMA)

    def fechar(self) -> None:
        self._con.close()

    def abrir_execucao(self, execucao_id: str, inicio: str, modo: str) -> None:
        with self._con:
            self._con.execute("INSERT INTO execucoes (id, inicio, modo, status) VALUES (?,?,?,?)",
                              (execucao_id, inicio, modo, "EM_ANDAMENTO"))

    def fechar_execucao(self, execucao_id: str, **campos) -> None:
        colunas = ", ".join(f"{c} = ?" for c in campos)
        with self._con:
            self._con.execute(f"UPDATE execucoes SET {colunas} WHERE id = ?",
                              (*campos.values(), execucao_id))

    def gravar_medicao(self, **m) -> None:
        colunas = ", ".join(m)
        marcas = ", ".join("?" for _ in m)
        with self._con:
            self._con.execute(f"INSERT INTO medicoes ({colunas}) VALUES ({marcas})", tuple(m.values()))

    def criticas_consecutivas(self, codigo_linha: int, codigo_parada: int, limite: int) -> int:
        """Quantas das últimas medições (da mais recente para trás) foram críticas, sem interrupção."""
        linhas = self._con.execute(
            "SELECT classificacao FROM medicoes WHERE codigo_linha = ? AND codigo_parada = ? "
            "ORDER BY id DESC LIMIT ?", (codigo_linha, codigo_parada, limite)).fetchall()
        total = 0
        for registro in linhas:
            if registro["classificacao"] not in CRITICAS:
                break
            total += 1
        return total

    def gravar_alerta(self, **a) -> bool:
        """Grava o alerta. Devolve False se já existe um para a mesma linha/parada no dia."""
        colunas = ", ".join(a)
        marcas = ", ".join("?" for _ in a)
        try:
            with self._con:
                self._con.execute(f"INSERT INTO alertas ({colunas}) VALUES ({marcas})", tuple(a.values()))
            return True
        except sqlite3.IntegrityError:
            return False

    def medicoes_da_execucao(self, execucao_id: str) -> list[dict]:
        return [dict(r) for r in self._con.execute(
            "SELECT linha, codigo_linha, codigo_parada, nome_parada, intervalo_programado_min, "
            "espera_min, intervalo_observado_min, indicador_min, razao, classificacao, detalhe, "
            "coletado_em FROM medicoes WHERE execucao_id = ? ORDER BY id", (execucao_id,))]

    def alertas_do_dia(self, data_ref: str) -> list[dict]:
        return [dict(r) for r in self._con.execute(
            "SELECT criado_em, linha, codigo_parada, nome_parada, tipo, mensagem, reclamacao "
            "FROM alertas WHERE data_ref = ? ORDER BY id DESC", (data_ref,))]

    def ultimas_execucoes(self, limite: int = 20) -> list[dict]:
        return [dict(r) for r in self._con.execute(
            "SELECT * FROM execucoes ORDER BY inicio DESC LIMIT ?", (limite,))]


def publicar_painel(caminho: Path, conteudo: dict) -> None:
    """Escrita atômica: o MVP nunca lê um arquivo pela metade."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporario, caminho)
