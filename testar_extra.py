"""Diagnóstico 2: população do IBGE e destino das emendas (documentos). Salva em teste_extra_resultado.txt.
Rodar:  python testar_extra.py   (depois da coleta, com dados/verba.db criado)
"""
import json
import sqlite3

import requests

from coletor.api import ErroAPI, PortalTransparencia

saida = []


def log(titulo, conteudo):
    saida.append(f"===== {titulo} =====\n{conteudo}\n")
    print(f"ok: {titulo}")


# 1) IBGE - população (dois caminhos)
for nome, url in [
    ("IBGE agregados", "https://servicodados.ibge.gov.br/api/v3/agregados/4709/periodos/2022/variaveis/93"
                       "?localidades=N6[4104808|4105003]"),
    ("IBGE SIDRA", "https://apisidra.ibge.gov.br/values/t/4709/n6/4104808,4105003/v/93/p/2022"),
]:
    try:
        r = requests.get(url, timeout=60)
        log(nome, f"HTTP {r.status_code}\n{r.text[:1500]}")
    except Exception as e:
        log(nome, f"FALHOU: {e}")

# 2) Documentos das emendas
try:
    con = sqlite3.connect("dados/verba.db")
    codigos = [r[0] for r in con.execute(
        "SELECT codigo FROM emendas WHERE localidade LIKE 'PARAN%(UF)' ORDER BY pago DESC LIMIT 2")]
    codigos += [r[0] for r in con.execute(
        "SELECT codigo FROM emendas WHERE municipio_codigo IS NOT NULL ORDER BY pago DESC LIMIT 1")]
    api = PortalTransparencia()
    for cod in codigos:
        try:
            docs = api.get(f"emendas/documentos/{cod}", pagina=1)
            log(f"Documentos da emenda {cod} ({len(docs)} na 1ª página)", json.dumps(docs[:3], ensure_ascii=False, indent=1))
        except ErroAPI as e:
            log(f"Documentos da emenda {cod}", f"ERRO: {e}")
except Exception as e:
    log("Documentos", f"FALHOU: {e}")

with open("teste_extra_resultado.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(saida))
print("Resultado salvo em teste_extra_resultado.txt")
