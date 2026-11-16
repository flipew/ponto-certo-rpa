"""Orquestração do processo de ponta a ponta.

    1. Carrega e valida a lista de linhas monitoradas
    2. Autentica na fonte de dados
    3. Para cada linha: coleta a previsão, calcula o indicador e classifica
    4. Decide se gera alerta (situação crítica persistente e ainda sem alerta no dia)
    5. Publica o resultado para o MVP (SQLite + JSON) e registra o resumo na auditoria

Códigos de saída: 0 concluída | 1 concluída com falhas parciais | 2 autenticação
| 3 fonte indisponível | 4 configuração inválida | 5 erro inesperado
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from . import regras
from .auditoria import Auditoria
from .config import FUSO, Config, ErroConfiguracao
from .entrada import LinhaMonitorada, carregar_linhas
from .olho_vivo import (ClienteOlhoVivo, ErroApiIndisponivel, ErroAutenticacao,
                        ErroOlhoVivo)
from .saida import Armazenamento, publicar_painel
from .simulador import ClienteSimulado


@dataclass
class Resultado:
    execucao_id: str
    status: str
    codigo_saida: int
    contadores: dict = field(default_factory=dict)


def criar_cliente(cfg: Config, agora):
    if cfg.modo == "real":
        return ClienteOlhoVivo(cfg.token, cfg.base_url, cfg.timeout_s, cfg.tentativas, cfg.espera_base_s)
    return ClienteSimulado.de_arquivo(cfg.arquivo_cenario, agora)


def montar_reclamacao(linha: LinhaMonitorada, av: regras.Avaliacao, momento: datetime, consecutivas: int) -> tuple[str, str]:
    """Devolve (mensagem curta para o painel, texto estruturado da reclamação para o SP156)."""
    quando = f"{momento:%d/%m/%Y} às {momento:%H:%M}"
    if av.classificacao == regras.SEM_PREVISAO:
        fato = "não havia nenhum ônibus previsto para a parada"
        curta = f"Linha {linha.linha}: nenhum ônibus previsto em {linha.nome_parada}"
    else:
        fato = (f"o intervalo observado foi de {av.indicador_min} min, "
                f"{f'{av.razao:.1f}'.replace('.', ',')} vezes o programado")
        curta = (f"Linha {linha.linha}: {av.indicador_min} min de intervalo em {linha.nome_parada} "
                 f"(programado: {linha.intervalo_programado_min:g} min)")
    texto = (
        f"Assunto: intervalo excessivo entre ônibus.\n"
        f"Linha: {linha.linha}. Parada: {linha.nome_parada} (código {linha.codigo_parada}).\n"
        f"Data e hora da verificação: {quando}.\n"
        f"Intervalo programado: {linha.intervalo_programado_min:g} min.\n"
        f"Ocorrência: {fato}, em {consecutivas} verificações consecutivas.\n"
        f"Solicitação: verificar o cumprimento das viagens programadas da linha.\n"
        f"Fonte dos dados: API Olho Vivo (SPTrans), coleta automatizada Ponto Certo."
    )
    return curta, texto


def executar(cfg: Config, cliente=None, agora=None, eco: bool = True) -> Resultado:
    agora = agora or (lambda: datetime.now(FUSO))
    inicio = agora()
    execucao_id = f"{inicio:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    aud = Auditoria(cfg.dir_logs, execucao_id, agora, eco)
    arm = Armazenamento(cfg.banco)
    cont = {"linhas_lidas": 0, "rejeitadas": 0, "processadas": 0, "falhas": 0, "alertas": 0}
    fonte = None

    def encerrar(status: str, codigo: int) -> Resultado:
        arm.fechar_execucao(execucao_id, fim=agora().isoformat(timespec="seconds"), fonte=fonte,
                            status=status, codigo_saida=codigo, **cont)
        registrar = aud.info if codigo == 0 else aud.aviso if codigo == 1 else aud.erro
        registrar("EXECUCAO_ENCERRADA", status=status, codigo_saida=codigo, **cont)
        return Resultado(execucao_id, status, codigo, dict(cont))

    try:
        arm.abrir_execucao(execucao_id, inicio.isoformat(timespec="seconds"), cfg.modo)
        aud.info("EXECUCAO_INICIADA", modo=cfg.modo, arquivo_linhas=cfg.arquivo_linhas.name)

        # 1. Entrada ---------------------------------------------------------------
        try:
            linhas, rejeitadas = carregar_linhas(cfg.arquivo_linhas)
            cliente = cliente or criar_cliente(cfg, agora)
        except ErroConfiguracao as erro:
            aud.erro("CONFIGURACAO_INVALIDA", motivo=str(erro))
            return encerrar("ABORTADA_CONFIGURACAO", 4)
        fonte = getattr(cliente, "fonte", "desconhecida")
        cont["linhas_lidas"] = len(linhas) + len(rejeitadas)
        cont["rejeitadas"] = len(rejeitadas)
        for rej in rejeitadas:
            aud.aviso("REGISTRO_REJEITADO", linha_csv=rej.numero_linha_csv, conteudo=rej.conteudo,
                      motivo=rej.motivo)
        aud.info("ENTRADA_CARREGADA", validas=len(linhas), rejeitadas=len(rejeitadas), fonte=fonte)

        # 2. Autenticação ----------------------------------------------------------
        try:
            cliente.autenticar()
        except ErroAutenticacao as erro:
            aud.erro("FALHA_AUTENTICACAO", motivo=str(erro))
            return encerrar("ABORTADA_AUTENTICACAO", 2)
        except ErroApiIndisponivel as erro:
            aud.erro("FONTE_INDISPONIVEL", etapa="autenticacao", motivo=str(erro))
            return encerrar("ABORTADA_FONTE_INDISPONIVEL", 3)
        aud.info("AUTENTICADO", fonte=fonte)

        # 3 e 4. Repetição sobre a coleção de linhas, com decisão por linha -----------
        for linha in linhas:
            momento = agora()
            base = dict(execucao_id=execucao_id, coletado_em=momento.isoformat(timespec="seconds"),
                        linha=linha.linha, codigo_linha=linha.codigo_linha,
                        codigo_parada=linha.codigo_parada, nome_parada=linha.nome_parada,
                        intervalo_programado_min=linha.intervalo_programado_min)
            try:
                resposta = cliente.previsao(linha.codigo_parada, linha.codigo_linha)
                chegadas = regras.interpretar_previsao(resposta, linha.codigo_linha)
            except ErroOlhoVivo as erro:
                cont["falhas"] += 1
                arm.gravar_medicao(**base, classificacao=regras.FALHA_COLETA,
                                   detalhe=f"{type(erro).__name__}: {erro}")
                aud.erro("FALHA_COLETA", linha=linha.linha, codigo_parada=linha.codigo_parada,
                         tipo=type(erro).__name__, motivo=str(erro))
                continue  # uma linha com problema não interrompe as demais

            av = regras.classificar(chegadas, linha.intervalo_programado_min,
                                    cfg.limite_atencao, cfg.limite_critico)
            arm.gravar_medicao(**base, espera_min=av.espera_min,
                               intervalo_observado_min=av.intervalo_observado_min,
                               indicador_min=av.indicador_min, razao=av.razao,
                               classificacao=av.classificacao)
            cont["processadas"] += 1
            aud.info("LINHA_PROCESSADA", linha=linha.linha, codigo_parada=linha.codigo_parada,
                     classificacao=av.classificacao, indicador_min=av.indicador_min,
                     programado_min=linha.intervalo_programado_min, razao=av.razao)

            if av.classificacao not in regras.CRITICAS:
                continue
            consecutivas = arm.criticas_consecutivas(linha.codigo_linha, linha.codigo_parada,
                                                     cfg.execucoes_para_alerta)
            if consecutivas < cfg.execucoes_para_alerta:
                aud.info("ALERTA_AGUARDANDO_CONFIRMACAO", linha=linha.linha,
                         criticas_consecutivas=consecutivas, necessarias=cfg.execucoes_para_alerta)
                continue
            curta, texto = montar_reclamacao(linha, av, momento, consecutivas)
            novo = arm.gravar_alerta(criado_em=momento.isoformat(timespec="seconds"),
                                     data_ref=f"{momento:%Y-%m-%d}", execucao_id=execucao_id,
                                     linha=linha.linha, codigo_linha=linha.codigo_linha,
                                     codigo_parada=linha.codigo_parada, nome_parada=linha.nome_parada,
                                     tipo=av.classificacao, mensagem=curta, reclamacao=texto)
            if novo:
                cont["alertas"] += 1
                aud.aviso("ALERTA_GERADO", linha=linha.linha, tipo=av.classificacao, mensagem=curta)
            else:
                aud.info("ALERTA_DUPLICADO_IGNORADO", linha=linha.linha,
                         motivo="já existe alerta para esta linha e parada hoje")

        # 5. Saída para o MVP -------------------------------------------------------
        if cont["falhas"] == 0:
            status, codigo = "CONCLUIDA", 0
        elif cont["processadas"] == 0:
            status, codigo = "FALHA_TOTAL_COLETA", 3
        else:
            status, codigo = "CONCLUIDA_COM_FALHAS", 1

        medicoes = arm.medicoes_da_execucao(execucao_id)
        resumo = {classe.lower(): sum(1 for m in medicoes if m["classificacao"] == classe)
                  for classe in (regras.NORMAL, regras.ATENCAO, regras.CRITICO,
                                 regras.SEM_PREVISAO, regras.FALHA_COLETA)}
        fim = agora()
        publicar_painel(cfg.painel_json, {
            "gerado_em": fim.isoformat(timespec="seconds"), "execucao_id": execucao_id,
            "modo": cfg.modo, "fonte": fonte, "status_execucao": status,
            "resumo": {"linhas_monitoradas": len(medicoes), **resumo},
            "linhas": medicoes, "alertas_do_dia": arm.alertas_do_dia(f"{fim:%Y-%m-%d}"),
        })
        aud.info("PAINEL_PUBLICADO", arquivo=cfg.painel_json.name, linhas=len(medicoes))
        return encerrar(status, codigo)

    except Exception as erro:  # nada falha em silêncio: registra, encerra e devolve código 5
        aud.erro("ERRO_INESPERADO", tipo=type(erro).__name__, detalhe=str(erro)[:200])
        try:
            return encerrar("ERRO_INESPERADO", 5)
        except Exception:
            return Resultado(execucao_id, "ERRO_INESPERADO", 5, dict(cont))
    finally:
        arm.fechar()
