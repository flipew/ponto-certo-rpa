# Testes e evidências

## Como rodar

```bash
pip install -r requirements.txt
python -m pytest -v
```

Resultado registrado em [`evidencias/pytest_saida.txt`](evidencias/pytest_saida.txt): **44 testes, 44 aprovados**.
Os testes usam relógio controlado, pastas temporárias e sessão HTTP falsa. Não acessam a rede.

## Cenários exigidos

| Cenário | Teste | O que comprova |
| --- | --- | --- |
| Sucesso | `test_robo.py::test_sucesso_processa_todas_e_entrega_ao_mvp` | 3 linhas processadas, painel JSON e banco gravados, log completo, código 0 |
| Decisão | `test_robo.py::test_decisao_alerta_so_com_critico_persistente_e_sem_duplicar` | 1ª medição crítica aguarda, 2ª gera alerta, 3ª não duplica |
| Decisão | `test_robo.py::test_decisao_medicao_normal_interrompe_a_sequencia` | medição normal zera a contagem de críticas |
| Decisão | `test_regras.py::test_classificacao_por_faixa` | limites NORMAL, ATENCAO e CRITICO, inclusive o valor exato do limite |
| Falha | `test_robo.py::test_falha_em_uma_linha_nao_interrompe_as_demais` | API fora do ar e resposta inválida viram `FALHA_COLETA`, as outras linhas seguem, código 1 |
| Falha | `test_robo.py::test_falha_de_autenticacao_aborta_com_codigo_2` | token recusado aborta sem gravar medições |
| Falha | `test_olho_vivo.py::test_recupera_apos_falhas_transitorias_com_espera_crescente` | repetição com espera de 1 s e 2 s recupera a consulta |
| Falha | `test_entrada.py::test_rejeita_invalidos_e_duplicados_com_motivo` | registros inválidos e duplicados rejeitados com motivo |
| Segurança | `test_olho_vivo.py::test_mensagens_de_erro_nunca_carregam_o_token` | o token não vaza em mensagens de erro |

## Execuções de demonstração (modo simulado)

- [`evidencias/demonstracao_3_execucoes.txt`](evidencias/demonstracao_3_execucoes.txt): três execuções seguidas do cenário padrão. A 1ª aguarda confirmação, a 2ª gera 2 alertas, a 3ª ignora os duplicados.
- [`evidencias/falhas_que_abortam.txt`](evidencias/falhas_que_abortam.txt): token ausente (código 2) e arquivo de linhas ausente (código 4).
- [`../logs/amostra_auditoria.jsonl`](../logs/amostra_auditoria.jsonl): log de auditoria dessas três execuções.
- [`../assets/amostra_painel_linhas.json`](../assets/amostra_painel_linhas.json): painel entregue ao MVP na 3ª execução.

## O que não foi testado

A chamada à API Olho Vivo real. O cliente foi escrito a partir da documentação da SPTrans e
testado com sessão HTTP falsa. Antes da entrega, rode `python rpa.py executar --modo real`
com um token válido e códigos de linha e parada reais.
