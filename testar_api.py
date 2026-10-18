"""Teste rápido da API: busca 2 emendas e 1 convênio de Cascavel e salva em teste_api_resultado.txt.

Como usar:
1. Crie o arquivo chave_api.txt nesta pasta e cole SÓ a chave dentro (Bloco de Notas).
2. Rode:  python testar_api.py
3. Mande para o Claude o conteúdo de teste_api_resultado.txt (não contém a chave).
"""
import json
import os

from coletor.api import ErroAPI, PortalTransparencia, ler_chave_arquivo

# Diagnóstico da chave (sem mostrar a chave)
env = os.environ.get("PORTAL_API_KEY", "")
if "COLE_SUA" in env.upper():
    print("Ignorando PORTAL_API_KEY do terminal (era o texto de exemplo).")
    env = ""
arq = ler_chave_arquivo()
if env:
    print(f"ATENÇÃO: o terminal tem PORTAL_API_KEY definida ({len(env)} caracteres) e ela tem prioridade.")
    print("Se for a chave errada, feche este terminal (lixeira) e abra um novo, ou rode: Remove-Item Env:PORTAL_API_KEY")
if arq:
    avisos = []
    if any(c.isspace() for c in arq):
        avisos.append("tem espaço ou quebra de linha no meio")
    if len(arq) != 32:
        avisos.append("a chave costuma ter 32 caracteres — confira")
    print(f"chave lida do chave_api.txt: {len(arq)} caracteres, começa com '{arq[:4]}…' e termina com '…{arq[-4:]}'"
          + (f" — PROBLEMA: {', '.join(avisos)}" if avisos else ""))
elif not env:
    print("Não achei a chave: crie chave_api.txt nesta pasta com a chave dentro.")

try:
    api = PortalTransparencia()
    emendas = api.get("emendas", ano=2025, pagina=1)[:2]
    convenios = api.get("convenios", codigoIBGE="4104808", pagina=1)[:1]
    texto = ("EMENDAS:\n" + json.dumps(emendas, ensure_ascii=False, indent=1) +
             "\n\nCONVENIOS:\n" + json.dumps(convenios, ensure_ascii=False, indent=1))
    print("Deu certo! A API respondeu.")
except ErroAPI as e:
    texto = f"ERRO: {e}"
    print(texto)

with open("teste_api_resultado.txt", "w", encoding="utf-8") as f:
    f.write(texto)
print("Resultado salvo em teste_api_resultado.txt")
