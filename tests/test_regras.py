"""Cenários de DECISÃO: a regra de negócio isolada."""
import pytest

from ponto_certo import regras
from ponto_certo.olho_vivo import ErroRespostaInvalida


def resposta(hr, horarios, cl=1273):
    return {"hr": hr, "p": {"cp": 1, "np": "X", "l": [{"cl": cl, "vs": [{"p": "1", "t": t} for t in horarios]}]}}


@pytest.mark.parametrize("chegadas, programado, esperado, indicador", [
    ([3, 8], 6, regras.NORMAL, 5),         # razão 0,83
    ([7], 6, regras.NORMAL, 7),            # razão 1,17: ainda dentro da tolerância
    ([11, 19], 8, regras.ATENCAO, 11),     # razão 1,38
    ([12, 20], 6, regras.ATENCAO, 12),     # razão 2,00: limite exato fica em ATENCAO
    ([24, 51], 10, regras.CRITICO, 27),    # razão 2,70
])
def test_classificacao_por_faixa(chegadas, programado, esperado, indicador):
    av = regras.classificar(chegadas, programado)
    assert av.classificacao == esperado
    assert av.indicador_min == indicador


def test_sem_onibus_previsto_e_tratado_como_critico():
    av = regras.classificar([], 10)
    assert av.classificacao == regras.SEM_PREVISAO
    assert av.classificacao in regras.CRITICAS
    assert av.razao is None


def test_limites_sao_configuraveis():
    assert regras.classificar([10], 8, limite_atencao=1.5).classificacao == regras.NORMAL


def test_interpreta_horarios_em_minutos():
    assert regras.interpretar_previsao(resposta("20:09", ["20:15", "20:31"]), 1273) == [6, 22]


def test_virada_da_meia_noite():
    assert regras.interpretar_previsao(resposta("23:55", ["00:05"]), 1273) == [10]


def test_previsao_ja_vencida_conta_como_chegando():
    assert regras.interpretar_previsao(resposta("20:09", ["20:08"]), 1273) == [0]


def test_parada_sem_previsao_devolve_lista_vazia():
    assert regras.interpretar_previsao({"hr": "20:09", "p": None}, 1273) == []


def test_ignora_outras_linhas_da_mesma_parada():
    r = resposta("20:00", ["20:04"], cl=999)
    assert regras.interpretar_previsao(r, 1273) == []


@pytest.mark.parametrize("ruim", [
    None, [], {"mensagem": "erro"}, {"hr": "20h09", "p": None}, {"hr": "25:00", "p": None},
    {"hr": "20:00", "p": "texto"}, {"hr": "20:00", "p": {"l": [{"cl": 1273, "vs": [{"p": "1"}]}]}},
])
def test_resposta_fora_do_formato_gera_erro_tipado(ruim):
    with pytest.raises(ErroRespostaInvalida):
        regras.interpretar_previsao(ruim, 1273)
