"""Linha de comando do robô Ponto Certo.

    python rpa.py executar                      # modo simulado (demonstração)
    python rpa.py executar --modo real          # API Olho Vivo (exige OLHO_VIVO_TOKEN)
    python rpa.py executar --repetir-min 5      # execução contínua, a cada 5 minutos
    python rpa.py servir                        # API de leitura + tela do MVP
    python rpa.py descobrir --linha 8000        # ajuda a achar códigos de linha e de parada
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .config import RAIZ, ErroConfiguracao, carregar_config
from .olho_vivo import ClienteOlhoVivo, ErroOlhoVivo
from .robo import executar


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="rpa.py", description="Ponto Certo RPA")
    sub = p.add_subparsers(dest="comando", required=True)

    e = sub.add_parser("executar", help="roda o processo de monitoramento")
    e.add_argument("--modo", choices=["simulado", "real"])
    e.add_argument("--linhas", type=Path, help="CSV de linhas monitoradas")
    e.add_argument("--cenario", type=Path, help="JSON do cenário (modo simulado)")
    e.add_argument("--repetir-min", type=float, default=0, help="repete a cada N minutos (0 = uma vez)")
    e.add_argument("--max-ciclos", type=int, default=0, help="limite de ciclos ao repetir (0 = sem limite)")

    s = sub.add_parser("servir", help="sobe a API de leitura para o MVP")
    s.add_argument("--porta", type=int, default=8000)

    d = sub.add_parser("descobrir", help="consulta códigos de linha e paradas na API real")
    d.add_argument("--linha", required=True, help="letreiro ou termo, ex.: 8000")
    return p.parse_args()


def _config_execucao(a: argparse.Namespace):
    cfg = carregar_config(modo=a.modo, arquivo_cenario=a.cenario)
    linhas = a.linhas
    if linhas is None:  # cada modo tem a sua lista padrão
        linhas = (RAIZ / "config" / "linhas_monitoradas.csv" if cfg.modo == "real"
                  else RAIZ / "simulacao" / "linhas_demo.csv")
    return carregar_config(modo=cfg.modo, arquivo_cenario=a.cenario, arquivo_linhas=linhas)


def main() -> int:
    a = _args()
    try:
        if a.comando == "servir":
            from .api import servir
            servir(carregar_config(), a.porta)
            return 0

        if a.comando == "descobrir":
            cfg = carregar_config(modo="real")
            cliente = ClienteOlhoVivo(cfg.token, cfg.base_url, cfg.timeout_s, cfg.tentativas, cfg.espera_base_s)
            cliente.autenticar()
            for linha in cliente.buscar_linha(a.linha):
                print(json.dumps(linha, ensure_ascii=False))
                for parada in cliente.paradas_por_linha(linha.get("cl"))[:15]:
                    print("   parada:", json.dumps(parada, ensure_ascii=False))
            return 0

        cfg = _config_execucao(a)
        ciclo = 0
        while True:
            ciclo += 1
            resultado = executar(cfg)
            if a.repetir_min <= 0 or (a.max_ciclos and ciclo >= a.max_ciclos):
                return resultado.codigo_saida
            if resultado.codigo_saida in (2, 4):  # erro que repetir não resolve
                return resultado.codigo_saida
            time.sleep(a.repetir_min * 60)
    except ErroConfiguracao as erro:
        print(f"ERRO de configuração: {erro}", file=sys.stderr)
        return 4
    except ErroOlhoVivo as erro:
        print(f"ERRO na API Olho Vivo: {erro}", file=sys.stderr)
        return 3
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
