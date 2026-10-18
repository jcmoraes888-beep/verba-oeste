"""Transforma as respostas da API em linhas limpas para o banco.

A API devolve valores como texto no formato brasileiro ("1.234.567,89") e nomes de campos
que variam entre versões — por isso a leitura é tolerante (vários nomes possíveis por campo).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def chave_nome(s: str) -> str:
    """'Céu Azul' → 'CEU AZUL' (para casar nomes de municípios)."""
    s = sem_acento(s).upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def valor(v) -> float:
    """'1.234,56' → 1234.56 · '-1.000,00' → -1000.0 · 1234.5 → 1234.5 · None/'' → 0.0"""
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("R$", "").replace(" ", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


def campo(d: dict, *nomes, padrao=None):
    """Primeiro campo existente; aceita caminhos com ponto ('convenente.nome')."""
    for nome in nomes:
        atual = d
        for parte in nome.split("."):
            if isinstance(atual, dict) and parte in atual:
                atual = atual[parte]
            else:
                atual = None
                break
        if atual not in (None, ""):
            return atual
    return padrao


def data(v) -> str | None:
    if not v:
        return None
    s = str(v)[:10]
    for f in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, f).date().isoformat()
        except ValueError:
            pass
    return None


# ------------------------------------------------------------------ emendas
_LOCAL = re.compile(r"^(.*?)\s*[-–(]\s*([A-Z]{2})\)?\s*$")


def municipio_da_localidade(localidade: str, indice: dict[str, str], uf: str = "PR") -> str | None:
    """'CASCAVEL - PR' → código IBGE de Cascavel, se estiver no índice {chave_nome: código}."""
    if not localidade:
        return None
    m = _LOCAL.match(sem_acento(localidade).upper().strip())
    if not m or m.group(2) != uf:
        return None
    return indice.get(chave_nome(m.group(1)))


def emenda(item: dict, indice: dict[str, str]) -> dict:
    local = campo(item, "localidadeDoGasto", "localidade", padrao="") or ""
    return {
        "codigo": str(campo(item, "codigoEmenda", "codigo", padrao="")),
        "ano": int(campo(item, "ano", padrao=0) or 0),
        "tipo": campo(item, "tipoEmenda", padrao="") or "",
        "autor": (campo(item, "nomeAutor", "autor", padrao="") or "").strip(),
        "numero": str(campo(item, "numeroEmenda", padrao="") or ""),
        "localidade": local,
        "municipio_codigo": municipio_da_localidade(local, indice),
        "funcao": campo(item, "funcao", "nomeFuncao", padrao="") or "",
        "subfuncao": campo(item, "subfuncao", "nomeSubfuncao", padrao="") or "",
        "empenhado": valor(campo(item, "valorEmpenhado")),
        "liquidado": valor(campo(item, "valorLiquidado")),
        "pago": valor(campo(item, "valorPago")),
        "resto_pago": valor(campo(item, "valorRestoPago")),
    }


def localidade_ampla(item: dict) -> bool:
    """Emendas com destino 'MÚLTIPLO' ou 'Nacional' (o dinheiro pode ir para várias cidades)."""
    local = sem_acento(campo(item, "localidadeDoGasto", "localidade", padrao="") or "").upper()
    return "MULTIPLO" in local or "NACIONAL" in local


def emenda_e_da_uf(item: dict, uf: str = "PR") -> bool:
    local = sem_acento(campo(item, "localidadeDoGasto", "localidade", padrao="") or "").upper()
    return local.endswith(f"- {uf}") or local.endswith(f"({uf})") or "PARANA (UF)" in local


# ------------------------------------------------------------------ pagamentos de emendas
def municipio_do_favorecido(nome: str, uf: str, indice: dict[str, str], uf_alvo: str = "PR") -> str | None:
    """'MUNICIPIO DE TOLEDO' / 'FUNDO MUNICIPAL DE SAUDE DE CASCAVEL' → código IBGE (se for da região)."""
    if (uf or "").upper() not in (uf_alvo, "PARANA", "PARANÁ"):
        return None
    n = " " + chave_nome(nome) + " "
    for chave in sorted(indice, key=len, reverse=True):     # nomes longos primeiro ("SANTA TEREZA DO OESTE")
        if n.endswith(" " + chave + " ") or f" DE {chave} " in n or f" DO {chave} " in n:
            return indice[chave]
    return None


_AUTOR = re.compile(r"^\s*(\d+)\s*-\s*(.+)$")


def e_pagamento_de_emenda(det: dict) -> bool:
    """Documentos de despesa trazem 'autor': '3176 - FULANO' quando vêm de emenda; '0000' quando não."""
    m = _AUTOR.match(str(campo(det, "autor", padrao="") or ""))
    return bool(m) and int(m.group(1)) != 0


def tipo_pelo_pagamento(det: dict) -> str:
    """Tipo da emenda deduzido do próprio pagamento (quando não sabemos o código da emenda)."""
    acao = sem_acento(str(campo(det, "acao", padrao="") or "")).upper()
    autor = sem_acento(str(campo(det, "autor", padrao="") or "")).upper()
    if "ESPECIA" in acao:
        return "Emenda Individual - Transferências Especiais"
    if "BANCADA" in autor:
        return "Emenda de Bancada"
    if "COMISS" in autor:
        return "Emenda de Comissão"
    return "Emenda Individual - Transferências com Finalidade Definida"


def pagamento(det: dict, emenda_codigo: str, indice: dict[str, str]) -> dict:
    """Detalhe de um documento de pagamento (despesas/documentos/{codigo})."""
    v = valor(campo(det, "valor"))
    especie = sem_acento(str(campo(det, "especie", padrao="") or "")).upper()
    if "ESTORNO" in especie or "ANULA" in especie or "CANCELA" in especie:
        v = -abs(v)
    d = data(campo(det, "data"))
    nome = campo(det, "nomeFavorecido", padrao="") or ""
    return {
        "documento": str(campo(det, "documento", "codigoDocumento", padrao="")),
        "emenda_codigo": emenda_codigo, "data": d, "ano": int(d[:4]) if d else 0, "valor": v,
        "favorecido": nome, "cnpj": campo(det, "codigoFavorecido", padrao="") or "",
        "municipio_codigo": municipio_do_favorecido(nome, campo(det, "ufFavorecido", padrao=""), indice),
        "autor": re.sub(r"^\d+\s*-\s*", "", str(campo(det, "autor", padrao="") or "")).strip(),
        "observacao": campo(det, "observacao", padrao="") or "",
        "funcao": re.sub(r"^\d+\s*-\s*", "", str(campo(det, "funcao", padrao="") or "")).strip(),
        "tipo": tipo_pelo_pagamento(det),
    }


def so_digitos(s) -> str:
    return "".join(c for c in str(s or "") if c.isdigit())


# ------------------------------------------------------------------ convênios
def _texto(v) -> str:
    """Garante texto simples (a API às vezes devolve objeto no lugar de texto)."""
    if isinstance(v, dict):
        v = v.get("descricao") or v.get("nome") or ""
    return str(v or "").strip()


def convenio(item: dict, codigo_ibge: str) -> dict:
    inicio = data(campo(item, "dataInicioVigencia"))
    return {
        "id": str(campo(item, "id", "dimConvenio.codigo", "dimConvenio.numero", padrao="")),
        "numero": str(campo(item, "dimConvenio.numero", "numero", padrao="") or ""),
        "objeto": (campo(item, "dimConvenio.objeto", "objeto", padrao="") or "").strip(),
        "situacao": _texto(campo(item, "situacao", padrao="")).capitalize(),
        "tipo_instrumento": _texto(campo(item, "tipoInstrumento.descricao", "tipoInstrumento", padrao="")),
        # agrupa pelo ministério (órgão máximo); se não houver, usa o órgão
        "orgao": _texto(campo(item, "orgao.orgaoMaximo.nome", "orgao.nome", "unidadeGestora.orgaoMaximo.nome",
                              padrao="")),
        "convenente": campo(item, "convenente.nome", padrao="") or "",
        "municipio_codigo": str(campo(item, "municipioConvenente.codigoIBGE", padrao=codigo_ibge)),
        "valor": valor(campo(item, "valor", "valorTotal")),
        "valor_liberado": valor(campo(item, "valorLiberado")),
        "contrapartida": valor(campo(item, "valorContrapartida")),
        "inicio_vigencia": inicio,
        "fim_vigencia": data(campo(item, "dataFinalVigencia", "dataFimVigencia")),
        "ultima_liberacao": data(campo(item, "dataUltimaLiberacao")),
        "ano": int(inicio[:4]) if inicio else 0,
    }


def hoje_iso() -> str:
    return date.today().isoformat()
