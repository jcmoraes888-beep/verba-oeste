"""Banco SQLite do projeto (um arquivo só: dados/verba.db)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CAMINHO_PADRAO = RAIZ / "dados" / "verba.db"
CAMINHO_DEMO = RAIZ / "dados" / "demo.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS municipios (
  codigo_ibge TEXT PRIMARY KEY, nome TEXT NOT NULL, uf TEXT, populacao INTEGER
);
CREATE TABLE IF NOT EXISTS emendas (
  codigo TEXT PRIMARY KEY, ano INTEGER, tipo TEXT, autor TEXT, numero TEXT, localidade TEXT,
  municipio_codigo TEXT, funcao TEXT, subfuncao TEXT,
  empenhado REAL, liquidado REAL, pago REAL, resto_pago REAL
);
CREATE INDEX IF NOT EXISTS ix_emendas_mun ON emendas(municipio_codigo, ano);
CREATE TABLE IF NOT EXISTS convenios (
  id TEXT PRIMARY KEY, numero TEXT, objeto TEXT, situacao TEXT, tipo_instrumento TEXT, orgao TEXT,
  convenente TEXT, municipio_codigo TEXT, valor REAL, valor_liberado REAL, contrapartida REAL,
  inicio_vigencia TEXT, fim_vigencia TEXT, ultima_liberacao TEXT, ano INTEGER
);
CREATE INDEX IF NOT EXISTS ix_conv_mun ON convenios(municipio_codigo, ano);
CREATE TABLE IF NOT EXISTS emendas_pagamentos (
  documento TEXT PRIMARY KEY, emenda_codigo TEXT, data TEXT, ano INTEGER, valor REAL,
  favorecido TEXT, cnpj TEXT, municipio_codigo TEXT, autor TEXT, observacao TEXT, funcao TEXT, tipo TEXT
);
CREATE INDEX IF NOT EXISTS ix_pag_mun ON emendas_pagamentos(municipio_codigo, ano);
CREATE TABLE IF NOT EXISTS emendas_docs_lidos (emenda_codigo TEXT, documento TEXT, PRIMARY KEY (emenda_codigo, documento));
CREATE TABLE IF NOT EXISTS cnpjs_municipio (cnpj TEXT PRIMARY KEY, municipio_codigo TEXT, origem TEXT);
CREATE TABLE IF NOT EXISTS coletas (
  fonte TEXT, quando TEXT, registros INTEGER, observacao TEXT
);
CREATE TABLE IF NOT EXISTS meta (chave TEXT PRIMARY KEY, valor TEXT);
"""


def conectar(caminho: Path | str = CAMINHO_PADRAO) -> sqlite3.Connection:
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho)
    con.executescript(ESQUEMA)
    _migrar(con)
    return con


def _migrar(con: sqlite3.Connection):
    """Acrescenta colunas novas em bancos criados por versões anteriores."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(emendas_pagamentos)")}
    for c in ("funcao", "tipo"):
        if c not in cols:
            con.execute(f"ALTER TABLE emendas_pagamentos ADD COLUMN {c} TEXT")
    con.commit()


def upsert(con: sqlite3.Connection, tabela: str, linhas: list[dict], substituir: bool = True) -> int:
    """Grava as linhas. substituir=False mantém o que já existe (INSERT OR IGNORE)."""
    if not linhas:
        return 0
    cols = list(linhas[0])
    sql = f"INSERT OR {'REPLACE' if substituir else 'IGNORE'} INTO {tabela} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})"
    con.executemany(sql, [tuple(l[c] for c in cols) for l in linhas])
    con.commit()
    return len(linhas)


def set_meta(con, chave: str, valor: str):
    con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (chave, valor))
    con.commit()


def get_meta(con, chave: str) -> str | None:
    r = con.execute("SELECT valor FROM meta WHERE chave = ?", (chave,)).fetchone()
    return r[0] if r else None
