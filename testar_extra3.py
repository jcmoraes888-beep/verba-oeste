"""Diagnóstico 4: por que chegou pouco dinheiro de emenda na região? Salva em teste_extra3_resultado.txt.
Rodar:  python testar_extra3.py      (leva uns 3 minutos)
"""
import json
from collections import Counter, defaultdict

from coletor import normalizar as n
from coletor.api import ErroAPI, PortalTransparencia

api = PortalTransparencia()
saida = []

# 1) Todas as emendas de 2025: como a "localidade do gasto" aparece?
qtd, pago, tipos = Counter(), defaultdict(float), Counter()
exemplos = defaultdict(list)
total = 0
for e in api.emendas(2025):
    total += 1
    loc = n.sem_acento(str(e.get("localidadeDoGasto", ""))).upper()
    cat = ("PARANA (UF)" if "PARANA (UF)" in loc else "MUNICIPIO-PR" if loc.endswith("- PR") else
           "NACIONAL" if "NACIONAL" in loc else "MULTIPLO" if "MULTIPLO" in loc else
           "REGIAO" if "REGIAO" in loc else "OUTRA UF" if ("(UF)" in loc or loc[-5:-2] == " - ") else "OUTRO")
    qtd[cat] += 1
    pago[cat] += n.valor(e.get("valorPago"))
    tipos[(cat, e.get("tipoEmenda", ""))] += 1
    if len(exemplos[cat]) < 4:
        exemplos[cat].append(e.get("localidadeDoGasto"))
saida.append(f"===== emendas 2025: {total} itens lidos =====")
for cat in qtd:
    saida.append(f"{cat:14s} qtd={qtd[cat]:6d}  pago=R$ {pago[cat]/1e6:,.1f} mi   ex: {exemplos[cat]}")
saida.append("--- por tipo ---")
for (cat, t), q in sorted(tipos.items()):
    saida.append(f"{cat:14s} {t}: {q}")

# 2) Documentos recebidos pela Prefeitura de Cascavel (busca pelo favorecido)
for params in [dict(codigoPessoa="76208867000107", fase=3, ano=2025, pagina=1),
               dict(codigoPessoa="76.208.867/0001-07", fase=3, ano=2025, pagina=1)]:
    try:
        r = api.get("despesas/documentos-por-favorecido", **params)
        saida.append(f"===== documentos-por-favorecido {params['codigoPessoa']}: {len(r)} itens =====\n"
                     + json.dumps(r[:3], ensure_ascii=False, indent=1)[:2500])
        if r:
            cod = r[0].get("codigoDocumento") or r[0].get("documento")
            if cod:
                d = api.get(f"despesas/documentos/{cod}")
                saida.append("===== detalhe do 1º documento =====\n" + json.dumps(d, ensure_ascii=False, indent=1)[:2500])
        break
    except ErroAPI as e:
        saida.append(f"===== documentos-por-favorecido {params['codigoPessoa']}: ERRO {e} =====")

saida.append(f"\nRequisições: {api.requisicoes}")
with open("teste_extra3_resultado.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(saida))
print("Resultado salvo em teste_extra3_resultado.txt")
