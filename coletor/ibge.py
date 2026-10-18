"""Municípios e população (IBGE).

- Localidades: https://servicodados.ibge.gov.br/api/docs/localidades
- População: Censo 2022, tabela SIDRA 4709 (variável 93 — população residente).
"""
from __future__ import annotations

import requests

LOCALIDADES = "https://servicodados.ibge.gov.br/api/v1/localidades"
AGREGADOS = "https://servicodados.ibge.gov.br/api/v3/agregados"

# Mesorregião Oeste Paranaense
MESORREGIAO_OESTE_PR = 4106


def municipios(regiao: str = f"meso:{MESORREGIAO_OESTE_PR}", sessao=None) -> list[dict]:
    """regiao: 'meso:4106' (mesorregião), 'micro:41018' (microrregião) ou 'uf:41' (estado)."""
    s = sessao or requests
    tipo, codigo = regiao.split(":")
    caminho = {"meso": "mesorregioes", "micro": "microrregioes", "uf": "estados"}[tipo]
    r = s.get(f"{LOCALIDADES}/{caminho}/{codigo}/municipios", timeout=60)
    r.raise_for_status()
    out = []
    for m in r.json():
        uf = (m.get("microrregiao") or {}).get("mesorregiao", {}).get("UF", {}).get("sigla") or "PR"
        out.append({"codigo_ibge": str(m["id"]), "nome": m["nome"], "uf": uf})
    return out


def populacao_censo2022(codigos: list[str], sessao=None) -> dict[str, int]:
    """População residente do Censo 2022 (SIDRA, tabela 4709, variável 93).
    A API de agregados (servicodados v3) devolveu HTTP 500 nos testes; o SIDRA funciona."""
    s = sessao or requests
    pop: dict[str, int] = {}
    for i in range(0, len(codigos), 50):
        lote = ",".join(codigos[i:i + 50])
        r = s.get(f"https://apisidra.ibge.gov.br/values/t/4709/n6/{lote}/v/93/p/2022", timeout=60)
        r.raise_for_status()
        for linha in r.json()[1:]:          # a 1ª linha é o cabeçalho
            v = str(linha.get("V", ""))
            if v.isdigit():
                pop[str(linha["D1C"])] = int(v)
    return pop


SICONFI_ENTES = "https://apidatalake.tesouro.gov.br/ords/siconfi/tt/entes"


def cnpjs_municipios(codigos: list[str], sessao=None) -> dict[str, str]:
    """CNPJ da prefeitura de cada município (Tesouro Nacional — SICONFI, lista de entes).
    Devolve {cnpj só com dígitos: código IBGE}."""
    s = sessao or requests
    alvo = {str(c) for c in codigos}
    out: dict[str, str] = {}
    offset = 0
    while True:
        r = s.get(SICONFI_ENTES, params={"offset": offset, "limit": 5000}, timeout=90)
        r.raise_for_status()
        d = r.json()
        itens = d.get("items", []) if isinstance(d, dict) else d
        for e in itens:
            cod = str(e.get("cod_ibge", ""))
            cnpj = "".join(ch for ch in str(e.get("cnpj", "")) if ch.isdigit())
            if cod in alvo and len(cnpj) == 14:
                out[cnpj] = cod
        if not (isinstance(d, dict) and d.get("hasMore")) or not itens:
            return out
        offset += len(itens)
