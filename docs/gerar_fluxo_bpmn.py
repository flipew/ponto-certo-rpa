"""Gera docs/fluxo_bpmn.svg (notação BPMN) a partir de coordenadas fixas.

Uso: python docs/gerar_fluxo_bpmn.py   (PNG: rsvg-convert -z 2 docs/fluxo_bpmn.svg -o docs/fluxo_bpmn.png)
"""
from pathlib import Path

INK, EDGE, QUIET, ACCENT, RED = "#1c1e21", "#5f6368", "#5f6368", "#12355b", "#b3261e"
W, H = 132, 44
p: list[str] = []


def texto(x, y, linhas, tam=12, cor=INK, peso=400, ancora="middle"):
    y0 = y - (len(linhas) - 1) * 7 + tam / 3
    for i, linha in enumerate(linhas):
        p.append(f'<text x="{x}" y="{y0 + i * 14:.1f}" font-size="{tam}" fill="{cor}" '
                 f'font-weight="{peso}" text-anchor="{ancora}">{linha}</text>')


def tarefa(cx, cy, linhas, w=W, destaque=False):
    cor, larg, fundo = (ACCENT, 2, "#e8eef5") if destaque else (EDGE, 1.25, "#ffffff")
    p.append(f'<rect x="{cx - w / 2}" y="{cy - H / 2}" width="{w}" height="{H}" rx="8" '
             f'fill="{fundo}" stroke="{cor}" stroke-width="{larg}"/>')
    texto(cx, cy, linhas, peso=600 if destaque else 400)


def decisao(cx, cy, linhas):
    r = 22
    p.append(f'<polygon points="{cx - r},{cy} {cx},{cy - r} {cx + r},{cy} {cx},{cy + r}" '
             f'fill="#ffffff" stroke="{EDGE}" stroke-width="1.25"/>')
    p.append(f'<path d="M{cx - 7} {cy - 7}L{cx + 7} {cy + 7}M{cx + 7} {cy - 7}L{cx - 7} {cy + 7}" '
             f'stroke="{EDGE}" stroke-width="1.5"/>')
    texto(cx, cy - 36, linhas, tam=11.5, cor=INK, peso=600)


def inicio(cx, cy):
    p.append(f'<circle cx="{cx}" cy="{cy}" r="16" fill="#ffffff" stroke="{EDGE}" stroke-width="1.25"/>')
    p.append(f'<circle cx="{cx}" cy="{cy}" r="10" fill="none" stroke="{EDGE}" stroke-width="1"/>')
    p.append(f'<path d="M{cx} {cy - 6}V{cy}H{cx + 5}" fill="none" stroke="{EDGE}" stroke-width="1.25"/>')


def fim(cx, cy, cor=EDGE, r=14):
    p.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#ffffff" stroke="{cor}" stroke-width="3.5"/>')


def seta(d):
    p.append(f'<path d="{d}" fill="none" stroke="{EDGE}" stroke-width="1.25" marker-end="url(#seta)"/>')


def rotulo(x, y, t, ancora="middle"):
    texto(x, y, [t], tam=11.5, cor=QUIET, ancora=ancora)


p.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 600" font-family="Helvetica, Arial, sans-serif">')
p.append('<rect width="760" height="600" fill="#ffffff"/>')
p.append(f'<defs><marker id="seta" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" '
         f'orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{EDGE}"/></marker></defs>')
texto(24, 28, ["Ponto Certo RPA: monitoramento do intervalo das linhas (BPMN)"], tam=15, peso=600, ancora="start")

# Subprocesso de repetição
p.append(f'<rect x="24" y="262" width="712" height="214" rx="10" fill="#f6f8fb" stroke="{EDGE}" stroke-width="1.25"/>')
texto(40, 458, ["↻ Para cada linha monitorada (repetição)"], tam=12, peso=600, ancora="start")

# Conectores
seta("M66 100H114")                    # início -> carregar
seta("M246 100H318")                   # carregar -> entrada válida?
seta("M362 100H424")                   # sim -> autenticar
seta("M556 100H628")                   # autenticar -> autenticou?
seta("M340 122V168")                   # não -> registrar erro
seta("M650 122V190H406")               # não -> registrar erro
seta("M274 190H216")                   # registrar erro -> fim abortado
seta("M672 100H722V238H110V308")       # sim -> consultar previsão
seta("M176 330H248")                   # consultar -> coleta ok?
seta("M292 330H354")                   # sim -> calcular
seta("M486 330H558")                   # calcular -> crítico persistente?
seta("M270 352V398")                   # não -> registrar falha
seta("M336 420H386")                   # falha -> próxima linha
seta("M580 352V398")                   # sim -> gerar alerta
seta("M602 330H676")                   # não -> próxima linha
seta("M646 420H690V344")               # alerta -> próxima linha
seta("M200 476V518")                   # subprocesso -> publicar
seta("M295 540H364")                   # publicar -> resumo
seta("M496 540H584")                   # resumo -> fim

# Linha 1
inicio(50, 100)
rotulo(50, 134, "Agendamento")
tarefa(180, 100, ["Carregar e validar", "lista de linhas (CSV)"])
decisao(340, 100, ["Entrada válida?"])
tarefa(490, 100, ["Autenticar na", "API Olho Vivo"])
decisao(650, 100, ["Autenticou?"])
rotulo(392, 92, "sim")
rotulo(700, 92, "sim")
rotulo(350, 146, "não", "start")
rotulo(660, 146, "não", "start")

# Linha 2: caminho de erro
tarefa(340, 190, ["Registrar erro", "na auditoria"])
fim(200, 190, RED)
texto(176, 190, ["Execução abortada", "(códigos 2, 3 ou 4)"], tam=11.5, cor=QUIET, ancora="end")

# Linha 3: dentro da repetição
tarefa(110, 330, ["Consultar previsão", "(até 3 tentativas)"])
decisao(270, 330, ["Coleta ok?"])
tarefa(420, 330, ["Calcular indicador", "e classificar"])
decisao(580, 330, ["Crítico persistente e", "sem alerta hoje?"])
fim(690, 330, r=12)
texto(690, 302, ["Próxima linha"], tam=11.5, cor=QUIET)
rotulo(322, 322, "sim")
rotulo(638, 322, "não")
rotulo(280, 378, "não", "start")
rotulo(590, 378, "sim", "start")

# Linha 4
tarefa(270, 420, ["Registrar", "FALHA_COLETA"])
fim(400, 420, r=12)
texto(420, 420, ["Próxima linha"], tam=11.5, cor=QUIET, ancora="start")
tarefa(580, 420, ["Gerar alerta e texto", "da reclamação"])

# Linha 5: saída
tarefa(200, 540, ["Publicar painel para o MVP", "(JSON + SQLite)"], w=190, destaque=True)
tarefa(430, 540, ["Registrar resumo", "na auditoria"])
fim(600, 540)
texto(624, 540, ["Execução encerrada", "(códigos 0, 1 ou 3)"], tam=11.5, cor=QUIET, ancora="start")

p.append("</svg>")
destino = Path(__file__).with_name("fluxo_bpmn.svg")
destino.write_text("\n".join(p), encoding="utf-8")
print("gerado:", destino)
