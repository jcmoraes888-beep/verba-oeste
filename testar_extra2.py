"""Diagnóstico 3: recursos federais recebidos por município. Salva em teste_extra2_resultado.txt.
Rodar:  python testar_extra2.py
"""
import json

from coletor.api import ErroAPI, PortalTransparencia

api = PortalTransparencia()
saida = []
for formato in ["01/2025", "202501", "2025-01"]:
    fim = {"01/2025": "12/2025", "202501": "202512", "2025-01": "2025-12"}[formato]
    try:
        r = api.get("despesas/recursos-recebidos", mesAnoInicio=formato, mesAnoFim=fim, codigoIBGE="4104808", pagina=1)
        saida.append(f"===== recursos-recebidos Cascavel 2025 (formato {formato}) — {len(r)} itens =====\n"
                     + json.dumps(r[:6], ensure_ascii=False, indent=1))
        break
    except ErroAPI as e:
        saida.append(f"===== formato {formato}: ERRO {e} =====")
try:
    r = api.get("despesas/documentos/170860000012025OB003222")
    saida.append("===== documento de pagamento de emenda Pix =====\n" + json.dumps(r, ensure_ascii=False, indent=1)[:3000])
except ErroAPI as e:
    saida.append(f"===== documento: ERRO {e} =====")
with open("teste_extra2_resultado.txt", "w", encoding="utf-8") as f:
    f.write("\n\n".join(saida))
print("Resultado salvo em teste_extra2_resultado.txt")
