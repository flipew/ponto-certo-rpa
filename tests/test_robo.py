"""Fluxo completo (entrada -> coleta -> decisão -> saída), nos três cenários pedidos:
SUCESSO, DECISÃO e FALHA. Usa o cliente simulado e pastas temporárias."""
import json
import sqlite3
from dataclasses import replace

from conftest import CABECALHO
from ponto_certo.olho_vivo import ErroApiIndisponivel, ErroAutenticacao
from ponto_certo.robo import executar
from ponto_certo.simulador import ClienteSimulado

TUDO_NORMAL = {"1273": {"chegadas_min": [3, 8]}, "33715": {"chegadas_min": [4, 13]},
               "1877": {"chegadas_min": [5, 16]}}


def rodar(cfg, relogio, cenario, cliente=None):
    return executar(cfg, cliente or ClienteSimulado(cenario, relogio), agora=relogio, eco=False)


def eventos(cfg):
    linhas = []
    for arq in sorted(cfg.dir_logs.glob("auditoria-*.jsonl")):
        linhas += [json.loads(l) for l in arq.read_text(encoding="utf-8").splitlines()]
    return linhas


def consulta(cfg, sql):
    con = sqlite3.connect(cfg.banco)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


# ------------------------------------------------------------------ SUCESSO
def test_sucesso_processa_todas_e_entrega_ao_mvp(cfg, relogio):
    r = rodar(cfg, relogio, TUDO_NORMAL)

    assert (r.status, r.codigo_saida) == ("CONCLUIDA", 0)
    assert r.contadores == {"linhas_lidas": 3, "rejeitadas": 0, "processadas": 3, "falhas": 0, "alertas": 0}

    painel = json.loads(cfg.painel_json.read_text(encoding="utf-8"))  # o que o MVP lê
    assert painel["execucao_id"] == r.execucao_id
    assert painel["resumo"] == {"linhas_monitoradas": 3, "normal": 3, "atencao": 0, "critico": 0,
                                "sem_previsao": 0, "falha_coleta": 0}
    assert [l["linha"] for l in painel["linhas"]] == ["8000-10", "971D-10", "576M-10"]
    assert painel["alertas_do_dia"] == []

    assert consulta(cfg, "SELECT status, processadas, codigo_saida FROM execucoes") == [("CONCLUIDA", 3, 0)]
    nomes = [e["evento"] for e in eventos(cfg)]
    assert nomes[0] == "EXECUCAO_INICIADA" and nomes[-1] == "EXECUCAO_ENCERRADA"
    assert nomes.count("LINHA_PROCESSADA") == 3
    assert all(e["ts"] and e["execucao_id"] == r.execucao_id for e in eventos(cfg))


# ------------------------------------------------------------------ DECISÃO
def test_decisao_alerta_so_com_critico_persistente_e_sem_duplicar(cfg, relogio):
    critico = {**TUDO_NORMAL, "33715": {"chegadas_min": [24, 51]}}

    r1 = rodar(cfg, relogio, critico)                 # 1ª medição crítica: aguarda confirmação
    assert r1.contadores["alertas"] == 0
    assert "ALERTA_AGUARDANDO_CONFIRMACAO" in [e["evento"] for e in eventos(cfg)]

    relogio.avancar(5)
    r2 = rodar(cfg, relogio, critico)                 # 2ª seguida: gera o alerta
    assert r2.contadores["alertas"] == 1
    painel = json.loads(cfg.painel_json.read_text(encoding="utf-8"))
    alerta = painel["alertas_do_dia"][0]
    assert alerta["linha"] == "971D-10" and alerta["tipo"] == "CRITICO"
    assert "27 min" in alerta["mensagem"]
    assert "2 verificações consecutivas" in alerta["reclamacao"]

    relogio.avancar(5)
    r3 = rodar(cfg, relogio, critico)                 # 3ª: já alertou hoje, não duplica
    assert r3.contadores["alertas"] == 0
    assert consulta(cfg, "SELECT COUNT(*) FROM alertas") == [(1,)]
    assert "ALERTA_DUPLICADO_IGNORADO" in [e["evento"] for e in eventos(cfg)]


def test_decisao_medicao_normal_interrompe_a_sequencia(cfg, relogio):
    critico = {**TUDO_NORMAL, "33715": {"chegadas_min": [24, 51]}}
    rodar(cfg, relogio, critico)
    relogio.avancar(5)
    rodar(cfg, relogio, TUDO_NORMAL)                  # voltou ao normal
    relogio.avancar(5)
    r = rodar(cfg, relogio, critico)                  # crítico de novo, mas não é consecutivo
    assert r.contadores["alertas"] == 0
    assert consulta(cfg, "SELECT COUNT(*) FROM alertas") == [(0,)]


def test_decisao_sem_onibus_previsto_tambem_alerta(cfg, relogio):
    vazio = {**TUDO_NORMAL, "1877": {"chegadas_min": []}}
    rodar(cfg, relogio, vazio)
    relogio.avancar(5)
    r = rodar(cfg, relogio, vazio)
    assert r.contadores["alertas"] == 1
    assert consulta(cfg, "SELECT tipo FROM alertas") == [("SEM_PREVISAO",)]


# ------------------------------------------------------------------ FALHA
def test_falha_em_uma_linha_nao_interrompe_as_demais(cfg, relogio):
    cenario = {**TUDO_NORMAL, "33715": {"erro": "indisponivel"}, "1877": {"erro": "resposta_invalida"}}
    r = rodar(cfg, relogio, cenario)

    assert (r.status, r.codigo_saida) == ("CONCLUIDA_COM_FALHAS", 1)
    assert r.contadores["processadas"] == 1 and r.contadores["falhas"] == 2
    falhas = [e for e in eventos(cfg) if e["evento"] == "FALHA_COLETA"]
    assert {f["tipo"] for f in falhas} == {"ErroApiIndisponivel", "ErroRespostaInvalida"}
    assert all(f["nivel"] == "ERRO" and f["motivo"] for f in falhas)
    painel = json.loads(cfg.painel_json.read_text(encoding="utf-8"))  # o MVP fica sabendo da falha
    assert painel["resumo"]["falha_coleta"] == 2


def test_falha_total_devolve_codigo_3(cfg, relogio):
    cenario = {k: {"erro": "indisponivel"} for k in TUDO_NORMAL}
    r = rodar(cfg, relogio, cenario)
    assert (r.status, r.codigo_saida) == ("FALHA_TOTAL_COLETA", 3)


class ClienteQueFalhaNoLogin:
    fonte = "teste"

    def __init__(self, erro):
        self.erro = erro

    def autenticar(self):
        raise self.erro


def test_falha_de_autenticacao_aborta_com_codigo_2(cfg, relogio):
    r = rodar(cfg, relogio, {}, ClienteQueFalhaNoLogin(ErroAutenticacao("Token recusado pela API Olho Vivo")))
    assert (r.status, r.codigo_saida) == ("ABORTADA_AUTENTICACAO", 2)
    assert consulta(cfg, "SELECT COUNT(*) FROM medicoes") == [(0,)]
    assert eventos(cfg)[-1]["nivel"] == "ERRO"


def test_fonte_fora_do_ar_no_login_aborta_com_codigo_3(cfg, relogio):
    r = rodar(cfg, relogio, {}, ClienteQueFalhaNoLogin(ErroApiIndisponivel("sem resposta")))
    assert (r.status, r.codigo_saida) == ("ABORTADA_FONTE_INDISPONIVEL", 3)


def test_arquivo_de_linhas_ausente_aborta_com_codigo_4(cfg, relogio):
    r = rodar(replace(cfg, arquivo_linhas=cfg.arquivo_linhas.with_name("sumiu.csv")), relogio, TUDO_NORMAL)
    assert (r.status, r.codigo_saida) == ("ABORTADA_CONFIGURACAO", 4)
    assert consulta(cfg, "SELECT status FROM execucoes") == [("ABORTADA_CONFIGURACAO",)]


def test_registros_invalidos_e_duplicados_sao_auditados(cfg, relogio):
    cfg.arquivo_linhas.write_text(CABECALHO + "8000-10,1273,4200953,LAPA,6\n"
                                  "8000-10,1273,4200953,LAPA,6\n9999-10,abc,1,X,10\n", encoding="utf-8")
    r = rodar(cfg, relogio, TUDO_NORMAL)
    assert r.contadores["rejeitadas"] == 2 and r.contadores["processadas"] == 1
    assert [e["motivo"][:9] for e in eventos(cfg) if e["evento"] == "REGISTRO_REJEITADO"] == ["duplicado", "codigo_li"]


def test_erro_inesperado_e_registrado_e_devolve_codigo_5(cfg, relogio):
    class ClienteComDefeito(ClienteSimulado):
        def previsao(self, codigo_parada, codigo_linha):
            raise RuntimeError("defeito qualquer")

    r = rodar(cfg, relogio, {}, ClienteComDefeito({}, relogio))
    assert (r.status, r.codigo_saida) == ("ERRO_INESPERADO", 5)
    assert "ERRO_INESPERADO" in [e["evento"] for e in eventos(cfg)]


# ------------------------------------------------------------------ SEGURANÇA
def test_logs_nao_expoem_segredos(cfg, relogio):
    from ponto_certo.auditoria import Auditoria
    aud = Auditoria(cfg.dir_logs, "x", relogio, eco=False)
    aud.info("TESTE", token="abc123", olho_vivo_token="abc123", linha="8000-10")
    bruto = aud.arquivo.read_text(encoding="utf-8")
    assert "abc123" not in bruto and "8000-10" in bruto
