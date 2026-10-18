"""Gera dados/demo.db com dados FICTÍCIOS, só para o painel funcionar antes da chave da API.

Os nomes das cidades são reais para dar contexto, mas TODOS os valores, autores e convênios são inventados.
Rodar: python -m dados.gerar_demo
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from coletor import banco

CIDADES = [  # (nome, população aproximada — fictícia para a demonstração)
    ("Cascavel", 348000), ("Foz do Iguaçu", 285000), ("Toledo", 150000), ("Marechal Cândido Rondon", 55000),
    ("Medianeira", 54000), ("Palotina", 34000), ("Assis Chateaubriand", 34000), ("Guaíra", 32000),
    ("Santa Helena", 26000), ("São Miguel do Iguaçu", 26000), ("Matelândia", 17000), ("Corbélia", 16000),
    ("Capitão Leônidas Marques", 16000), ("Guaraniaçu", 13000), ("Três Barras do Paraná", 12000),
    ("Céu Azul", 11000), ("Santa Tereza do Oeste", 10000), ("Catanduvas", 10000), ("Vera Cruz do Oeste", 9000),
    ("Ibema", 6000),
]
AUTORES = [f"DEP. FEDERAL EXEMPLO {c}" for c in "ABCDEFGH"] + ["SEN. EXEMPLO I", "SEN. EXEMPLO J",
                                                              "BANCADA DO PARANÁ (EXEMPLO)"]
FUNCOES = ["Saúde", "Educação", "Urbanismo", "Agricultura", "Assistência social", "Segurança pública",
           "Desporto e lazer", "Transporte"]
ORGAOS = ["Ministério da Saúde", "Fundo Nacional de Desenvolvimento da Educação", "Ministério das Cidades",
          "Ministério da Agricultura e Pecuária", "Ministério do Esporte", "Ministério da Integração"]
OBJETOS = {
    "Ministério da Saúde": ["Construção de Unidade Básica de Saúde", "Aquisição de equipamentos hospitalares",
                            "Reforma de posto de saúde"],
    "Fundo Nacional de Desenvolvimento da Educação": ["Construção de creche", "Aquisição de ônibus escolar",
                                                      "Cobertura de quadra escolar"],
    "Ministério das Cidades": ["Pavimentação asfáltica de vias urbanas", "Drenagem urbana",
                               "Revitalização de praça"],
    "Ministério da Agricultura e Pecuária": ["Aquisição de patrulha mecanizada", "Readequação de estradas rurais"],
    "Ministério do Esporte": ["Construção de academia ao ar livre", "Reforma de ginásio de esportes"],
    "Ministério da Integração": ["Recuperação de ponte", "Obras de contenção de encostas"],
}


def gerar(caminho=banco.CAMINHO_DEMO, anos=(2024, 2025, 2026), semente=42) -> int:
    rnd = random.Random(semente)
    if caminho.exists():
        caminho.unlink()
    con = banco.conectar(caminho)
    muns = [{"codigo_ibge": f"99{i:05d}", "nome": n, "uf": "PR", "populacao": p} for i, (n, p) in enumerate(CIDADES)]
    banco.upsert(con, "municipios", muns)
    hoje = date(2026, 10, 17)
    emendas, convenios = [], []
    k = 0
    for m in muns:
        peso = (m["populacao"] ** 0.55) / 40
        for ano in anos:
            for _ in range(rnd.randint(2, 7)):
                k += 1
                emp = round(rnd.uniform(0.3, 2.2) * peso * 80_000, 2)
                exec_ = rnd.uniform(0.15, 1.0) if ano == hoje.year else rnd.uniform(0.55, 1.0)
                pago = round(emp * exec_, 2)
                emendas.append({
                    "codigo": f"DEMO{k:05d}", "ano": ano, "tipo": rnd.choice(["Emenda Individual", "Emenda Individual",
                                                                             "Emenda de Bancada"]),
                    "autor": rnd.choice(AUTORES), "numero": f"{rnd.randint(1000, 9999)}",
                    "localidade": f"{m['nome'].upper()} - PR", "municipio_codigo": m["codigo_ibge"],
                    "funcao": rnd.choice(FUNCOES), "subfuncao": "", "empenhado": emp,
                    "liquidado": round(min(emp, pago * rnd.uniform(1.0, 1.15)), 2), "pago": pago, "resto_pago": 0.0})
            for _ in range(rnd.randint(1, 4)):
                k += 1
                org = rnd.choice(ORGAOS)
                ini = date(ano, rnd.randint(1, 12), rnd.randint(1, 28))
                fim = ini + timedelta(days=rnd.choice([365, 540, 730]))
                valor = round(rnd.uniform(0.2, 2.5) * peso * 100_000, 2)
                vencido = fim < hoje
                lib = rnd.uniform(0.0, 0.45) if (vencido and rnd.random() < 0.18) else rnd.uniform(0.5, 1.0) \
                    if vencido else rnd.uniform(0.0, 0.8)
                convenios.append({
                    "id": f"DEMO{k:05d}", "numero": f"{rnd.randint(900000, 999999)}",
                    "objeto": rnd.choice(OBJETOS[org]), "situacao": ("Concluído" if vencido and lib > 0.95 else
                                                                     "Em execução" if not vencido else
                                                                     "Prestação de contas em análise"),
                    "tipo_instrumento": rnd.choice(["Convênio", "Contrato de repasse"]), "orgao": org,
                    "convenente": f"MUNICÍPIO DE {m['nome'].upper()}", "municipio_codigo": m["codigo_ibge"],
                    "valor": valor, "valor_liberado": round(valor * lib, 2), "contrapartida": round(valor * 0.05, 2),
                    "inicio_vigencia": ini.isoformat(), "fim_vigencia": fim.isoformat(),
                    "ultima_liberacao": (ini + timedelta(days=rnd.randint(30, 300))).isoformat() if lib else None,
                    "ano": ano})
    banco.upsert(con, "emendas", emendas)
    tipos_demo = ["Emenda Individual - Transferências Especiais", "Emenda Individual - Transferências com Finalidade Definida",
                  "Emenda de Bancada"]
    pags = []
    for e in emendas:
        e_tipo = rnd.choice(tipos_demo)
        con.execute("UPDATE emendas SET tipo=? WHERE codigo=?", (e_tipo, e["codigo"]))
        if e["pago"] > 0:
            pags.append({"documento": "OB" + e["codigo"], "emenda_codigo": e["codigo"],
                         "data": f"{e['ano']}-{rnd.randint(3, 12):02d}-15", "ano": e["ano"], "valor": e["pago"],
                         "favorecido": f"MUNICIPIO DE {e['localidade'].replace(' - PR', '')}", "cnpj": "",
                         "municipio_codigo": e["municipio_codigo"], "autor": e["autor"], "observacao": ""})
    banco.upsert(con, "emendas_pagamentos", pags)
    banco.upsert(con, "convenios", convenios)
    banco.set_meta(con, "atualizado_em", "dados de exemplo")
    banco.set_meta(con, "regiao", "Oeste do Paraná (exemplo)")
    banco.set_meta(con, "anos", ",".join(map(str, anos)))
    banco.set_meta(con, "demo", "1")
    con.close()
    return len(emendas) + len(convenios)


if __name__ == "__main__":
    print(gerar(), "registros fictícios gerados em", banco.CAMINHO_DEMO)
