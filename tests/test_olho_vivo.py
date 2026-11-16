"""Cenários de FALHA do cliente da API real, com uma sessão HTTP falsa (sem rede)."""
import pytest
import requests

from ponto_certo.olho_vivo import (ClienteOlhoVivo, ErroApiIndisponivel,
                                   ErroAutenticacao, ErroRespostaInvalida)

TOKEN = "segredo-de-teste-123"


class Resp:
    def __init__(self, status=200, texto="true", corpo=None):
        self.status_code, self.text, self._corpo = status, texto, corpo

    def json(self):
        if self._corpo is None:
            raise ValueError("não é JSON")
        return self._corpo


class SessaoFalsa:
    def __init__(self, respostas):
        self.respostas, self.chamadas = list(respostas), []

    def request(self, metodo, url, params=None, timeout=None):
        self.chamadas.append((metodo, url, params))
        item = self.respostas.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def cliente(respostas, tentativas=3):
    sessao = SessaoFalsa(respostas)
    esperas = []
    c = ClienteOlhoVivo(TOKEN, "https://api.exemplo/v2.1", tentativas=tentativas,
                        sessao=sessao, dormir=esperas.append)
    return c, sessao, esperas


def test_autentica_com_post_e_token():
    c, sessao, _ = cliente([Resp(texto="true")])
    c.autenticar()
    assert sessao.chamadas == [("POST", "https://api.exemplo/v2.1/Login/Autenticar", {"token": TOKEN})]


def test_token_recusado():
    c, _, _ = cliente([Resp(texto="false")])
    with pytest.raises(ErroAutenticacao):
        c.autenticar()


def test_token_ausente_nem_chama_a_api():
    sessao = SessaoFalsa([])
    with pytest.raises(ErroAutenticacao, match="Token ausente"):
        ClienteOlhoVivo("", "https://api.exemplo", sessao=sessao).autenticar()
    assert sessao.chamadas == []


def test_recupera_apos_falhas_transitorias_com_espera_crescente():
    c, sessao, esperas = cliente([requests.ConnectionError("x"), Resp(status=503), Resp(corpo={"hr": "10:00", "p": None})])
    assert c.previsao(1, 2) == {"hr": "10:00", "p": None}
    assert len(sessao.chamadas) == 3
    assert esperas == [1.0, 2.0]


def test_desiste_apos_todas_as_tentativas():
    c, sessao, _ = cliente([requests.Timeout("x")] * 3)
    with pytest.raises(ErroApiIndisponivel, match="3 tentativas"):
        c.previsao(1, 2)
    assert len(sessao.chamadas) == 3


def test_corpo_que_nao_e_json():
    c, _, _ = cliente([Resp(corpo=None, texto="<html>manutenção</html>")])
    with pytest.raises(ErroRespostaInvalida, match="não é JSON"):
        c.previsao(1, 2)


def test_sessao_expirada_reautentica_uma_vez():
    c, sessao, _ = cliente([Resp(status=401), Resp(texto="true"), Resp(corpo={"hr": "10:00", "p": None})])
    assert c.previsao(1, 2)["hr"] == "10:00"
    assert [m for m, _, _ in sessao.chamadas] == ["GET", "POST", "GET"]


def test_mensagens_de_erro_nunca_carregam_o_token():
    erro_com_url = requests.ConnectionError(f"falha em /Login/Autenticar?token={TOKEN}")
    c, _, _ = cliente([erro_com_url] * 3)
    with pytest.raises(ErroApiIndisponivel) as info:
        c.autenticar()
    assert TOKEN not in str(info.value)
