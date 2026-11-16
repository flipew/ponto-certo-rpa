"""Validação da entrada: registro ruim é rejeitado e auditado, não derruba o lote."""
import pytest

from conftest import CABECALHO
from ponto_certo.config import ErroConfiguracao
from ponto_certo.entrada import carregar_linhas


def escrever(tmp_path, corpo, cabecalho=CABECALHO):
    arq = tmp_path / "l.csv"
    arq.write_text(cabecalho + corpo, encoding="utf-8")
    return arq


def test_linhas_validas(tmp_path):
    validas, rejeitadas = carregar_linhas(escrever(tmp_path, "8000-10,1273,4200953,LAPA,6\n175T-10,2506,34,SANTANA,7.5\n"))
    assert [v.linha for v in validas] == ["8000-10", "175T-10"]
    assert validas[1].intervalo_programado_min == 7.5
    assert rejeitadas == []


def test_rejeita_invalidos_e_duplicados_com_motivo(tmp_path):
    corpo = ("8000-10,1273,4200953,LAPA,6\n"
             "8000-10,1273,4200953,LAPA,6\n"      # duplicado
             "9999-10,abc,123,X,10\n"             # código não numérico
             "2002-10,2002,555,Y,\n"              # intervalo vazio
             "3003-10,3003,777,Z,0\n"             # intervalo fora da faixa
             "4004-10,4004,888,W,dez\n")          # intervalo não numérico
    validas, rejeitadas = carregar_linhas(escrever(tmp_path, corpo))
    assert len(validas) == 1
    motivos = [r.motivo for r in rejeitadas]
    assert len(motivos) == 5
    assert "duplicado" in motivos[0]
    assert "codigo_linha" in motivos[1]
    assert "vazio" in motivos[2]
    assert "fora da faixa" in motivos[3]
    assert "não numérico" in motivos[4]
    assert rejeitadas[0].numero_linha_csv == 3


def test_arquivo_ausente(tmp_path):
    with pytest.raises(ErroConfiguracao, match="não encontrado"):
        carregar_linhas(tmp_path / "nao_existe.csv")


def test_coluna_ausente(tmp_path):
    with pytest.raises(ErroConfiguracao, match="Colunas ausentes"):
        carregar_linhas(escrever(tmp_path, "8000-10,1273\n", cabecalho="linha,codigo_linha\n"))


def test_nenhuma_linha_valida(tmp_path):
    with pytest.raises(ErroConfiguracao, match="Nenhuma linha válida"):
        carregar_linhas(escrever(tmp_path, "x,abc,1,P,5\n"))
