import sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ponto_certo.config import FUSO, Config  # noqa: E402

CABECALHO = "linha,codigo_linha,codigo_parada,nome_parada,intervalo_programado_min\n"


class Relogio:
    """Relógio controlado: os testes não dependem da hora em que rodam."""

    def __init__(self):
        self.agora = datetime(2026, 11, 16, 8, 0, tzinfo=FUSO)

    def __call__(self):
        return self.agora

    def avancar(self, minutos):
        self.agora += timedelta(minutes=minutos)


@pytest.fixture
def relogio():
    return Relogio()


@pytest.fixture
def cfg(tmp_path):
    linhas = tmp_path / "linhas.csv"
    linhas.write_text(CABECALHO + "8000-10,1273,4200953,TERMINAL LAPA,6\n"
                                  "971D-10,33715,630012906,AV. IMIRIM,10\n"
                                  "576M-10,1877,7014417,VILA CLARA,12\n", encoding="utf-8")
    return replace(Config(), arquivo_linhas=linhas, dir_saida=tmp_path / "saida",
                   dir_logs=tmp_path / "logs", espera_base_s=0)
