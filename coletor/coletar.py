"""Coleta os dados da API e grava em dados/verba.db.

Uso:
    export PORTAL_API_KEY=suachave
    python -m coletor.coletar --anos 2024 2025 2026
    python -m coletor.coletar --anos 2026 --regiao uf:41      # todo o Paraná
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime

from coletor import banco, ibge, normalizar
from coletor.api import APIBloqueada, PortalTransparencia

log = logging.getLogger("coletor")


def coletar_municipios(con, regiao: str) -> dict[str, str]:
    """Lista de municípios do IBGE. Se o IBGE estiver fora do ar (acontece: timeouts vindos do GitHub
    Actions), usa os municípios já gravados no banco — a lista praticamente nunca muda."""
    salvos = {r[0]: (r[1], r[2], r[3]) for r in
              con.execute("SELECT codigo_ibge, nome, uf, populacao FROM municipios")}
    try:
        muns = ibge.municipios(regiao)
    except Exception as e:
        if not salvos or banco.get_meta(con, "regiao") not in (None, regiao):
            raise
        log.warning("IBGE indisponível (%s): usando os %d municípios já salvos no banco", e, len(salvos))
        return {normalizar.chave_nome(nome): cod for cod, (nome, _uf, _pop) in salvos.items()}
    try:
        pop = ibge.populacao_censo2022([m["codigo_ibge"] for m in muns])
    except Exception as e:  # população é opcional (só usada no "por habitante")
        log.warning("Sem população do IBGE: %s", e)
        pop = {}
    for m in muns:
        # sem resposta do SIDRA, mantém a população que já estava no banco (não apaga com NULL)
        m["populacao"] = pop.get(m["codigo_ibge"]) or (salvos.get(m["codigo_ibge"]) or (None, None, None))[2]
    banco.upsert(con, "municipios", muns)
    log.info("%d municípios", len(muns))
    return {normalizar.chave_nome(m["nome"]): m["codigo_ibge"] for m in muns}


def coletar_emendas(con, api: PortalTransparencia, anos: list[int], indice: dict[str, str], uf: str = "PR") -> int:
    """A API não filtra emendas por município: lê o ano inteiro e guarda
    (a) as com destino no PR e (b) as de destino 'MÚLTIPLO'/'Nacional' de autores do PR
    (é aí que está a maior parte do dinheiro: emendas Pix e fundo a fundo da saúde)."""
    total, amplas = 0, []
    for ano in anos:
        lote = []
        for item in api.emendas(ano):
            if normalizar.emenda_e_da_uf(item, uf):
                lote.append(normalizar.emenda(item, indice))
            elif normalizar.localidade_ampla(item):
                amplas.append(normalizar.emenda(item, indice))
            if len(lote) >= 500:
                total += banco.upsert(con, "emendas", lote)
                lote = []
        total += banco.upsert(con, "emendas", lote)
        log.info("Emendas %d: acumulado %d", ano, total)
    autores_uf = {r[0] for r in con.execute("SELECT DISTINCT autor FROM emendas WHERE autor <> ''")}
    escolhidas = [e for e in amplas if e["autor"] in autores_uf]
    total += banco.upsert(con, "emendas", escolhidas)
    log.info("Emendas 'MÚLTIPLO/Nacional' de autores do %s: %d (de %d)", uf, len(escolhidas), len(amplas))
    con.execute("INSERT INTO coletas VALUES (?,?,?,?)", ("emendas", datetime.now().isoformat(timespec="seconds"),
                                                          total, f"anos {anos}"))
    con.commit()
    return total


def coletar_pagamentos(con, api: PortalTransparencia, indice: dict[str, str], max_paginas: int = 40) -> int:
    """Para cada emenda do PR: lista os documentos, pega os de PAGAMENTO e lê o favorecido (a cidade que recebeu).
    É incremental: documentos já lidos são pulados, então as coletas diárias seguintes são rápidas."""
    lidos = {(a, b) for a, b in con.execute("SELECT emenda_codigo, documento FROM emendas_docs_lidos")}
    codigos = [r[0] for r in con.execute("SELECT codigo FROM emendas ORDER BY ano DESC")]
    novos = 0
    for i, cod in enumerate(codigos, 1):
        for doc in api.paginas(f"emendas/documentos/{cod}", max_paginas=max_paginas):
            fase = normalizar.sem_acento(str(doc.get("fase", ""))).upper()
            num = str(doc.get("codigoDocumento", ""))
            if fase != "PAGAMENTO" or not num or (cod, num) in lidos:
                continue
            try:
                det = api.get(f"despesas/documentos/{num}")
            except APIBloqueada:
                raise
            except Exception as e:  # um documento ruim não derruba a coleta
                log.warning("Documento %s: %s", num, e)
                continue
            linha = normalizar.pagamento(det if isinstance(det, dict) else {}, cod, indice)
            if linha["documento"]:
                banco.upsert(con, "emendas_pagamentos", [linha])
            con.execute("INSERT OR IGNORE INTO emendas_docs_lidos VALUES (?,?)", (cod, num))
            lidos.add((cod, num))
            novos += 1
        con.commit()
        if i % 25 == 0:
            log.info("Pagamentos: %d/%d emendas, %d documentos novos", i, len(codigos), novos)
    con.execute("INSERT INTO coletas VALUES (?,?,?,?)", ("pagamentos_emendas", datetime.now().isoformat(timespec="seconds"),
                                                          novos, f"{len(codigos)} emendas"))
    con.commit()
    log.info("Pagamentos de emendas: %d documentos novos", novos)
    return novos


def coletar_convenios(con, api: PortalTransparencia, anos: list[int], codigos: list[str]) -> int:
    total = 0
    ini, fim = f"01/01/{min(anos)}", f"31/12/{max(anos)}"
    for cod in codigos:
        linhas = [normalizar.convenio(i, cod) for i in api.convenios(cod, ini, fim)]
        total += banco.upsert(con, "convenios", linhas)
    con.execute("INSERT INTO coletas VALUES (?,?,?,?)", ("convenios", datetime.now().isoformat(timespec="seconds"),
                                                          total, f"{len(codigos)} municípios"))
    con.commit()
    log.info("Convênios: %d", total)
    return total


def coletar_recebidos(con, api: PortalTransparencia, anos: list[int], codigos: list[str], indice: dict[str, str]) -> int:
    """Do lado de quem RECEBE: todos os pagamentos federais feitos ao CNPJ da prefeitura (e dos fundos municipais
    já conhecidos) e que vieram de emenda. Pega também emendas que o caminho por emenda não alcança."""
    try:
        siconfi = ibge.cnpjs_municipios(codigos)
        banco.upsert(con, "cnpjs_municipio", [{"cnpj": c, "municipio_codigo": m, "origem": "siconfi"}
                                              for c, m in siconfi.items()])
        log.info("CNPJs de prefeituras (SICONFI): %d", len(siconfi))
    except Exception as e:  # sem SICONFI, segue com os CNPJs já aprendidos
        log.warning("Sem CNPJs do SICONFI: %s", e)
    aprendidos = [{"cnpj": normalizar.so_digitos(c), "municipio_codigo": m, "origem": "pagamentos"}
                  for c, m in con.execute("SELECT DISTINCT cnpj, municipio_codigo FROM emendas_pagamentos "
                                          "WHERE municipio_codigo IS NOT NULL")
                  if len(normalizar.so_digitos(c)) == 14]
    banco.upsert(con, "cnpjs_municipio", aprendidos, substituir=False)
    cnpjs = con.execute("SELECT cnpj, municipio_codigo FROM cnpjs_municipio WHERE municipio_codigo IN (%s)"
                        % ",".join("?" * len(codigos)), list(codigos)).fetchall()
    novos = 0
    for i, (cnpj, mun) in enumerate(cnpjs, 1):
        for ano in anos:
            lote = []
            try:
                for doc in api.paginas("despesas/documentos-por-favorecido", max_paginas=300,
                                       codigoPessoa=cnpj, fase=3, ano=ano):
                    if not normalizar.e_pagamento_de_emenda(doc):
                        continue
                    linha = normalizar.pagamento(doc, "", indice)
                    if linha["documento"]:
                        linha["municipio_codigo"] = mun    # o CNPJ já diz qual é a cidade
                        lote.append(linha)
            except APIBloqueada:
                con.commit()
                raise
            except Exception as e:  # um CNPJ com problema não derruba a coleta (o que já leu fica)
                log.warning("CNPJ %s, ano %s: %s", cnpj, ano, e)
            novos += banco.upsert(con, "emendas_pagamentos", lote, substituir=False)
        if i % 10 == 0:
            log.info("Recebidos: %d/%d CNPJs", i, len(cnpjs))
    # pagamentos achados pelo caminho da emenda cujo favorecido não tinha o nome da cidade
    # (ex.: "FUNDO MUNICIPAL DE SAUDE"): o CNPJ resolve
    con.execute("UPDATE emendas_pagamentos SET municipio_codigo = (SELECT c.municipio_codigo FROM cnpjs_municipio c "
                "WHERE c.cnpj = replace(replace(replace(emendas_pagamentos.cnpj, '.', ''), '/', ''), '-', '')) "
                "WHERE municipio_codigo IS NULL")
    con.execute("INSERT INTO coletas VALUES (?,?,?,?)", ("recebidos", datetime.now().isoformat(timespec="seconds"),
                                                          novos, f"{len(cnpjs)} CNPJs"))
    con.commit()
    log.info("Pagamentos de emenda recebidos pelas prefeituras/fundos: %d lidos", novos)
    return novos


def main(argv=None):
    p = argparse.ArgumentParser(description="Coleta emendas e convênios federais da região.")
    p.add_argument("--anos", type=int, nargs="+", default=[date.today().year - 2, date.today().year - 1, date.today().year])
    p.add_argument("--regiao", default=f"meso:{ibge.MESORREGIAO_OESTE_PR}")
    p.add_argument("--banco", default=str(banco.CAMINHO_PADRAO))
    p.add_argument("--so", choices=["emendas", "pagamentos", "recebidos", "convenios"], help="coletar só uma fonte")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    con = banco.conectar(a.banco)
    indice = coletar_municipios(con, a.regiao)
    api = PortalTransparencia()
    if a.so in (None, "emendas"):
        coletar_emendas(con, api, a.anos, indice)
    if a.so in (None, "emendas", "pagamentos"):
        coletar_pagamentos(con, api, indice)
    if a.so in (None, "emendas", "pagamentos", "recebidos"):
        coletar_recebidos(con, api, a.anos, list(indice.values()), indice)
    if a.so in (None, "convenios"):
        coletar_convenios(con, api, a.anos, list(indice.values()))
    banco.set_meta(con, "atualizado_em", datetime.now().isoformat(timespec="minutes"))
    banco.set_meta(con, "regiao", a.regiao)
    banco.set_meta(con, "anos", ",".join(map(str, a.anos)))
    banco.set_meta(con, "demo", "0")
    log.info("Pronto: %d requisições à API", api.requisicoes)


if __name__ == "__main__":
    main()
