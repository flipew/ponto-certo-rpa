"""API somente leitura para o MVP consumir o resultado da automação.

    GET /api/status      -> (ou /painel_linhas.json) último painel publicado (situação de cada linha)
    GET /api/alertas     -> alertas do dia (?data=AAAA-MM-DD para outra data)
    GET /api/execucoes   -> últimas execuções do robô (trilha de auditoria resumida)
    GET /                -> tela do MVP (mvp/index.html), que lê painel_linhas.json

Usa só a biblioteca padrão. Não aceita escrita: o MVP lê, o robô grava.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .config import FUSO, RAIZ, Config
from .saida import Armazenamento

PAGINA = RAIZ / "mvp" / "index.html"


def criar_handler(cfg: Config):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, corpo, status: int = 200) -> None:
            dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")  # dados públicos, só leitura
            self.send_header("Content-Length", str(len(dados)))
            self.end_headers()
            self.wfile.write(dados)

        def do_GET(self) -> None:  # noqa: N802 (nome exigido pela biblioteca)
            url = urlparse(self.path)
            consulta = parse_qs(url.query)
            if url.path in ("/api/status", "/painel_linhas.json"):
                if not cfg.painel_json.is_file():
                    return self._json({"erro": "nenhuma execução publicada ainda"}, 503)
                return self._json(json.loads(cfg.painel_json.read_text(encoding="utf-8")))
            if url.path in ("/api/alertas", "/api/execucoes"):
                if not cfg.banco.is_file():
                    return self._json({"erro": "nenhuma execução registrada ainda"}, 503)
                arm = Armazenamento(cfg.banco)
                try:
                    if url.path == "/api/execucoes":
                        return self._json(arm.ultimas_execucoes())
                    data = consulta.get("data", [f"{datetime.now(FUSO):%Y-%m-%d}"])[0]
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data):
                        return self._json({"erro": "data deve estar no formato AAAA-MM-DD"}, 400)
                    return self._json(arm.alertas_do_dia(data))
                finally:
                    arm.fechar()
            if url.path in ("/", "/index.html") and PAGINA.is_file():
                dados = PAGINA.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)
                return None
            return self._json({"erro": "rota não encontrada"}, 404)

        def log_message(self, formato, *args) -> None:
            print(f"[api] {self.address_string()} {formato % args}")

    return Handler


def servir(cfg: Config, porta: int = 8000) -> None:
    servidor = ThreadingHTTPServer(("0.0.0.0", porta), criar_handler(cfg))
    print(f"API Ponto Certo em http://localhost:{porta}  (Ctrl+C para encerrar)")
    try:
        servidor.serve_forever()
    finally:
        servidor.server_close()
