"""Consultas do painel (pandas sobre o SQLite)."""
from __future__ import annotations

import sqlite3
from datetime import date

import pandas as pd


def abrir(caminho) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{caminho}?mode=ro", uri=True, check_same_thread=False)


def meta(con) -> dict:
    return dict(con.execute("SELECT chave, valor FROM meta").fetchall())


def municipios(con) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM municipios ORDER BY nome", con)


def anos_disponiveis(con) -> list[int]:
    a = {r[0] for r in con.execute("SELECT DISTINCT ano FROM emendas UNION SELECT DISTINCT ano FROM convenios")}
    return sorted(x for x in a if x)


def _filtro(anos, codigos, t: str):
    w, p = [f"{t}.municipio_codigo IS NOT NULL"], []
    if anos:
        w.append(f"{t}.ano IN ({','.join('?' * len(anos))})")
        p += list(anos)
    if codigos:
        w.append(f"{t}.municipio_codigo IN ({','.join('?' * len(codigos))})")
        p += list(codigos)
    return " WHERE " + " AND ".join(w), p


def emendas(con, anos=None, codigos=None) -> pd.DataFrame:
    """Uma linha por PAGAMENTO de emenda a um município da região (cidade = favorecido do pagamento).
    Inclui as transferências especiais ("emendas Pix"), cujo destino oficial é só "PARANÁ (UF)"."""
    w, p = _filtro(anos, codigos, "p")
    return pd.read_sql(
        "SELECT p.documento, "
        # sem código da emenda (veio pelo CNPJ de quem recebeu): agrupa por autor + ano + área
        "COALESCE(NULLIF(p.emenda_codigo, ''), 'x:' || p.autor || ':' || p.ano || ':' || COALESCE(p.funcao, '')) AS codigo, "
        "p.ano, p.data, p.valor AS pago, p.favorecido, "
        "p.municipio_codigo, COALESCE(NULLIF(p.autor, ''), e.autor, '') AS autor, "
        "COALESCE(NULLIF(e.tipo, ''), p.tipo, '') AS tipo, "
        "COALESCE(NULLIF(e.funcao, ''), p.funcao, '') AS funcao, m.nome AS municipio "
        "FROM emendas_pagamentos p LEFT JOIN emendas e ON e.codigo = p.emenda_codigo "
        f"JOIN municipios m ON m.codigo_ibge = p.municipio_codigo{w}", con, params=p)


def tipo_curto(t: str) -> str:
    t = (t or "").lower()
    if "especia" in t:
        return "Transferência especial (Pix)"
    if "bancada" in t:
        return "Emenda de bancada"
    if "comiss" in t:
        return "Emenda de comissão"
    if "individual" in t:
        return "Emenda individual"
    return "Outras"


# situações que não representam dinheiro de verdade (registro anulado/excluído/cancelado)
SITUACOES_INVALIDAS = ("Convênio anulado", "Excluído", "Cancelado")


def convenios(con, anos=None, codigos=None) -> pd.DataFrame:
    w, p = _filtro(anos, codigos, "c")
    w += f" AND c.situacao NOT IN ({','.join('?' * len(SITUACOES_INVALIDAS))})"
    p += list(SITUACOES_INVALIDAS)
    return pd.read_sql(f"SELECT c.*, m.nome AS municipio FROM convenios c JOIN municipios m "
                       f"ON m.codigo_ibge = c.municipio_codigo{w}", con, params=p)


def ranking_municipios(em: pd.DataFrame, cv: pd.DataFrame, mun: pd.DataFrame) -> pd.DataFrame:
    """Por município: emendas pagas + convênios liberados, total e por habitante."""
    a = em.groupby("municipio_codigo", as_index=False).agg(emendas_pagas=("pago", "sum"),
                                                            qtd_emendas=("codigo", "nunique"))
    b = cv.groupby("municipio_codigo", as_index=False).agg(convenios_liberados=("valor_liberado", "sum"),
                                                           convenios_valor=("valor", "sum"),
                                                           qtd_convenios=("id", "count"))
    df = mun.rename(columns={"codigo_ibge": "municipio_codigo"}).merge(a, how="left").merge(b, how="left").fillna(
        {"emendas_pagas": 0, "qtd_emendas": 0, "convenios_liberados": 0,
         "convenios_valor": 0, "qtd_convenios": 0})
    df["total"] = df["emendas_pagas"] + df["convenios_liberados"]
    df["por_habitante"] = df["total"] / df["populacao"].where(df["populacao"] > 0)
    return df.sort_values("total", ascending=False)


def alertas_convenios(cv: pd.DataFrame, hoje: date | None = None, limite: float = 0.5) -> pd.DataFrame:
    """Convênios com vigência encerrada e menos de `limite` do valor liberado."""
    hoje = (hoje or date.today()).isoformat()
    if cv.empty:
        return cv
    d = cv[(cv["fim_vigencia"].notna()) & (cv["fim_vigencia"] < hoje) & (cv["valor"] > 0)].copy()
    d["pct_liberado"] = d["valor_liberado"] / d["valor"]
    return d[d["pct_liberado"] < limite].sort_values("valor", ascending=False)


def brl(v: float, curto: bool = False) -> str:
    v = float(v or 0)
    if curto:
        for div, suf in ((1e9, " bi"), (1e6, " mi"), (1e3, " mil")):
            if abs(v) >= div:
                return "R$ " + f"{v / div:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".") + suf
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
