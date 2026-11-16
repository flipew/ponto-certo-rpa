"""Cliente da API Olho Vivo (SPTrans) com repetição e erros tipados.

Documentação oficial: https://www.sptrans.com.br/desenvolvedores/
Fluxo: POST /Login/Autenticar?token=... (a sessão guarda o cookie) e depois
GET /Previsao?codigoParada=...&codigoLinha=...

Cuidado de segurança: as mensagens de erro nunca incluem a URL nem o texto da
exceção original, porque a URL de login carrega o token.
"""
from __future__ import annotations

import time

import requests


class ErroOlhoVivo(Exception):
    """Base dos erros de coleta."""


class ErroAutenticacao(ErroOlhoVivo):
    """Token ausente ou recusado. Não adianta repetir: a execução é abortada."""


class ErroApiIndisponivel(ErroOlhoVivo):
    """Sem resposta útil após todas as tentativas (timeout, conexão, HTTP 5xx)."""


class ErroRespostaInvalida(ErroOlhoVivo):
    """A API respondeu, mas o conteúdo não tem o formato esperado."""


class ClienteOlhoVivo:
    fonte = "api_olho_vivo"

    def __init__(self, token: str, base_url: str, timeout_s: float = 10.0, tentativas: int = 3,
                 espera_base_s: float = 1.0, sessao=None, dormir=time.sleep):
        self._token = token
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s
        self._tentativas = max(1, tentativas)
        self._espera = espera_base_s
        self._sessao = sessao or requests.Session()
        self._dormir = dormir

    def autenticar(self) -> None:
        if not self._token:
            raise ErroAutenticacao("Token ausente: defina OLHO_VIVO_TOKEN no ambiente ou no .env")
        resp = self._requisitar("POST", "/Login/Autenticar", {"token": self._token})
        if resp.status_code != 200 or resp.text.strip().lower() != "true":
            raise ErroAutenticacao("Token recusado pela API Olho Vivo")

    def previsao(self, codigo_parada: int, codigo_linha: int) -> dict:
        return self._get_json("/Previsao", {"codigoParada": codigo_parada, "codigoLinha": codigo_linha})

    def buscar_linha(self, termos: str) -> list:
        return self._get_json("/Linha/Buscar", {"termosBusca": termos})

    def paradas_por_linha(self, codigo_linha: int) -> list:
        return self._get_json("/Parada/BuscarParadasPorLinha", {"codigoLinha": codigo_linha})

    # ------------------------------------------------------------------ interno
    def _get_json(self, caminho: str, params: dict):
        resp = self._requisitar("GET", caminho, params)
        if resp.status_code == 401:  # sessão expirou: autentica de novo, uma vez
            self.autenticar()
            resp = self._requisitar("GET", caminho, params)
        if resp.status_code != 200:
            raise ErroRespostaInvalida(f"{caminho}: HTTP {resp.status_code}")
        try:
            return resp.json()
        except ValueError:
            raise ErroRespostaInvalida(f"{caminho}: corpo da resposta não é JSON") from None

    def _requisitar(self, metodo: str, caminho: str, params: dict):
        ultimo = "sem detalhe"
        for tentativa in range(1, self._tentativas + 1):
            try:
                resp = self._sessao.request(metodo, self._base + caminho, params=params,
                                            timeout=self._timeout)
                if resp.status_code < 500:
                    return resp
                ultimo = f"HTTP {resp.status_code}"
            except (requests.ConnectionError, requests.Timeout) as erro:
                ultimo = type(erro).__name__
            if tentativa < self._tentativas:
                self._dormir(self._espera * 2 ** (tentativa - 1))  # 1s, 2s, 4s...
        raise ErroApiIndisponivel(
            f"{caminho}: sem resposta após {self._tentativas} tentativas ({ultimo})")
