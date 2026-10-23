from datetime import date

import pytest

from coletor import banco, coletar, normalizar as N
from coletor.api import ErroAPI, PortalTransparencia
from painel import consultas as Q


def test_valor_brasileiro():
    assert N.valor("1.234.567,89") == 1234567.89
    assert N.valor("-1.000,00") == -1000.0
    assert N.valor("R$ 10,50") == 10.5
    assert N.valor(None) == 0.0 and N.valor("") == 0.0 and N.valor(12) == 12.0


def test_localidade_para_municipio():
    idx = {"CEU AZUL": "4105003", "CASCAVEL": "4104808", "FOZ DO IGUACU": "4108304"}
    assert N.municipio_da_localidade("CÉU AZUL - PR", idx) == "4105003"
    assert N.municipio_da_localidade("Foz do Iguaçu - PR", idx) == "4108304"
    assert N.municipio_da_localidade("CASCAVEL - SC", idx) is None      # outro estado
    assert N.municipio_da_localidade("PARANÁ (UF)", idx) is None
    assert N.municipio_da_localidade("Nacional", idx) is None


def test_emenda_e_convenio():
    idx = {"CASCAVEL": "4104808"}
    e = N.emenda({"codigoEmenda": "202612340001", "ano": 2026, "nomeAutor": " FULANO ", "localidadeDoGasto": "CASCAVEL - PR",
                  "funcao": "Saúde", "valorEmpenhado": "100.000,00", "valorPago": "40.000,00"}, idx)
    assert e["municipio_codigo"] == "4104808" and e["pago"] == 40000.0 and e["autor"] == "FULANO"
    assert N.emenda_e_da_uf({"localidadeDoGasto": "CASCAVEL - PR"}) and not N.emenda_e_da_uf({"localidadeDoGasto": "LAGES - SC"})
    c = N.convenio({"id": 9, "dimConvenio": {"numero": "900001", "objeto": "Creche"}, "orgao": {"nome": "FNDE"},
                    "valor": "1.000,00", "valorLiberado": "250,00", "dataInicioVigencia": "10/02/2025",
                    "dataFinalVigencia": "2026-01-31"}, "4104808")
    assert c["objeto"] == "Creche" and c["orgao"] == "FNDE" and c["ano"] == 2025
    assert c["fim_vigencia"] == "2026-01-31" and c["valor_liberado"] == 250.0


class Resp:
    def __init__(self, status, dados=None):
        self.status_code, self._d, self.text = status, dados, str(dados)

    def json(self):
        return self._d


class SessaoFalsa:
    def __init__(self, respostas):
        self.respostas, self.headers, self.chamadas = list(respostas), {}, []

    def get(self, url, params=None, timeout=None):
        self.chamadas.append((url, dict(params or {})))
        return self.respostas.pop(0)


def test_api_pagina_e_retentativa():
    s = SessaoFalsa([Resp(429), Resp(200, [{"a": 1}, {"a": 2}]), Resp(200, [{"a": 3}]), Resp(200, [])])
    dormidas = []
    api = PortalTransparencia("chave", sessao=s, dormir=dormidas.append)
    itens = list(api.emendas(2026))
    assert [i["a"] for i in itens] == [1, 2, 3]
    assert s.headers["chave-api-dados"] == "chave"
    assert 30 in dormidas                                     # esperou após o 429
    assert [c[1]["pagina"] for c in s.chamadas] == [1, 1, 2, 3]


def test_api_chave_recusada():
    api = PortalTransparencia("x", sessao=SessaoFalsa([Resp(401)]), dormir=lambda _: None)
    with pytest.raises(ErroAPI):
        api.get("emendas", pagina=1)


def test_coleta_ponta_a_ponta(tmp_path, monkeypatch):
    monkeypatch.setattr(coletar.ibge, "municipios", lambda regiao: [
        {"codigo_ibge": "4104808", "nome": "Cascavel", "uf": "PR"}, {"codigo_ibge": "4105003", "nome": "Céu Azul", "uf": "PR"}])
    monkeypatch.setattr(coletar.ibge, "populacao_censo2022", lambda c: {"4104808": 348000, "4105003": 11000})
    monkeypatch.setattr(coletar.ibge, "cnpjs_municipios", lambda c: {"11111111000111": "4105003"})

    class APIFalsa:
        requisicoes = 0

        def paginas(self, caminho, max_paginas=40, **kw):
            if caminho == "despesas/documentos-por-favorecido":       # prefeitura de Céu Azul
                return iter([{"documento": "OBCEU", "data": "01/03/2025", "valor": "1.000,00", "autor": "0000",
                              "nomeFavorecido": "MUNICIPIO DE CEU AZUL", "ufFavorecido": "PR"},
                             {"documento": "OBPIX", "data": "02/03/2025", "valor": "2.000,00",
                              "autor": "4321 - CICRANO", "acao": "0EC2 - TRANSFERENCIA ESPECIAL",
                              "funcao": "28 - Encargos especiais", "nomeFavorecido": "MUNICIPIO DE CEU AZUL",
                              "ufFavorecido": "PR", "codigoFavorecido": "11.111.111/0001-11"}])
            return iter([{"fase": "Pagamento", "codigoDocumento": f"OB{caminho[-1]}"}, {"fase": "Empenho", "codigoDocumento": "NE1"}])

        def get(self, caminho, **kw):
            return {"documento": caminho.split("/")[-1], "data": "12/09/2025", "valor": "4.950,00",
                    "nomeFavorecido": "MUNICIPIO DE CASCAVEL", "ufFavorecido": "PR", "autor": "3176 - FULANO",
                    "especie": "Original"}

        def emendas(self, ano):
            return iter([{"codigoEmenda": "1", "ano": ano, "localidadeDoGasto": "CÉU AZUL - PR", "valorEmpenhado": "10,00",
                          "valorPago": "5,00"},
                         {"codigoEmenda": "2", "ano": ano, "localidadeDoGasto": "LAGES - SC", "valorPago": "9,00"}])

        def convenios(self, cod, ini, fim):
            return iter([{"id": f"c{cod}", "valor": "100,00", "valorLiberado": "10,00", "dataInicioVigencia": "01/01/2024",
                          "dataFinalVigencia": "01/01/2025"}])

    monkeypatch.setattr(coletar, "PortalTransparencia", APIFalsa)
    db = tmp_path / "v.db"
    coletar.main(["--anos", "2025", "--banco", str(db)])
    con = Q.abrir(db)
    em = Q.emendas(con).sort_values("pago", ascending=False)               # pagamentos → cidade do favorecido
    assert len(em) == 2 and em.iloc[0]["municipio"] == "Cascavel" and em.iloc[0]["pago"] == 4950.0
    assert em.iloc[0]["autor"] == "FULANO"
    pix = em.iloc[1]                                                      # veio pelo CNPJ da prefeitura
    assert pix["municipio"] == "Céu Azul" and pix["autor"] == "CICRANO" and pix["pago"] == 2000.0
    assert Q.tipo_curto(pix["tipo"]) == "Transferência especial (Pix)" and pix["funcao"] == "Encargos especiais"
    cv = Q.convenios(con)
    assert len(cv) == 2
    assert len(Q.alertas_convenios(cv, hoje=date(2026, 10, 17))) == 2       # vencidos com 10% liberado
    assert Q.meta(con)["demo"] == "0"


def test_painel_com_demo(tmp_path):
    from dados import gerar_demo
    db = tmp_path / "d.db"
    gerar_demo.gerar(db)
    con = Q.abrir(db)
    rk = Q.ranking_municipios(Q.emendas(con, [2025]), Q.convenios(con, [2025]), Q.municipios(con))
    assert rk["total"].is_monotonic_decreasing and (rk["por_habitante"] > 0).all()
    assert Q.emendas(con)["pago"].sum() > 0
    assert Q.brl(1234567.8, curto=True) == "R$ 1,2 mi" and Q.brl(1234.5) == "R$ 1.234,50"


def test_formato_real_da_api():
    """Recorte real devolvido pela API em 18/10/2026 (convênio e emenda)."""
    import json
    conv = json.loads('''{"id": 352751569, "dataInicioVigencia": "2001-03-03", "dataFinalVigencia": "2006-03-30",
      "dataUltimaLiberacao": "2006-03-02", "dimConvenio": {"codigo": "412874", "objeto": "CONCESSÃO DE BOLSAS",
      "numero": "DS-03-02/2001"}, "situacao": "CONCLUÍDO", "convenente": {"nome": "FUNDACAO UNIVERSIDADE"},
      "municipioConvenente": {"codigoIBGE": "4104808", "nomeIBGE": "CASCAVEL"},
      "orgao": {"nome": "Fundação CAPES", "orgaoMaximo": {"codigo": "26000", "sigla": "MEC", "nome": "Ministério da Educação"}},
      "tipoInstrumento": {"id": 500001, "codigo": "1", "descricao": "CONVENIO"},
      "valor": 405211.32, "valorLiberado": 373044.48, "valorContrapartida": 0.0}''')
    c = N.convenio(conv, "4104808")
    assert c["tipo_instrumento"] == "CONVENIO" and c["orgao"] == "Ministério da Educação"
    assert c["situacao"] == "Concluído" and c["valor"] == 405211.32 and c["ano"] == 2001
    assert all(not isinstance(v, (dict, list)) for v in c.values())
    em = {"codigoEmenda": "202539940017", "ano": 2025, "nomeAutor": "X", "localidadeDoGasto": "RIO GRANDE DO NORTE (UF)",
          "valorEmpenhado": "39.989,35", "valorPago": "39.989,35"}
    assert not N.emenda_e_da_uf(em) and N.emenda(em, {})["pago"] == 39989.35


def test_populacao_sidra():
    from coletor import ibge

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"V": "Valor", "D1C": "Município (Código)"},
                    {"V": "348051", "D1C": "4104808"}, {"V": "10446", "D1C": "4105003"}]

    class S:
        def get(self, url, timeout=None):
            assert "4709/n6/4104808,4105003/v/93/p/2022" in url
            return R()

    assert ibge.populacao_censo2022(["4104808", "4105003"], sessao=S()) == {"4104808": 348051, "4105003": 10446}


def test_municipio_do_favorecido():
    idx = {"CASCAVEL": "1", "SANTA TEREZA DO OESTE": "2", "TOLEDO": "3", "CEU AZUL": "4"}
    assert N.municipio_do_favorecido("MUNICIPIO DE TOLEDO", "PR", idx) == "3"
    assert N.municipio_do_favorecido("FUNDO MUNICIPAL DE SAUDE DE CASCAVEL", "PR", idx) == "1"
    assert N.municipio_do_favorecido("MUNICÍPIO DE SANTA TEREZA DO OESTE", "PR", idx) == "2"
    assert N.municipio_do_favorecido("PREFEITURA MUNICIPAL DE CÉU AZUL", "PR", idx) == "4"
    assert N.municipio_do_favorecido("MUNICIPIO DE TOLEDO", "SC", idx) is None
    assert N.municipio_do_favorecido("MUNICIPIO DE CURITIBA", "PR", idx) is None
    p = N.pagamento({"documento": "X", "data": "12/09/2025", "valor": "1.000,00", "especie": "Estorno",
                     "nomeFavorecido": "MUNICIPIO DE TOLEDO", "ufFavorecido": "PR"}, "E1", idx)
    assert p["valor"] == -1000.0 and p["ano"] == 2025 and p["municipio_codigo"] == "3"


def test_emendas_multiplo_e_autor():
    assert N.localidade_ampla({"localidadeDoGasto": "MÚLTIPLO"}) and N.localidade_ampla({"localidadeDoGasto": "Nacional"})
    assert not N.localidade_ampla({"localidadeDoGasto": "CASCAVEL - PR"})
    assert N.e_pagamento_de_emenda({"autor": "3176 - DILCEU SPERAFICO"})
    assert not N.e_pagamento_de_emenda({"autor": "0000"}) and not N.e_pagamento_de_emenda({})
    assert N.tipo_pelo_pagamento({"autor": "7100 - BANCADA DO PARANA"}) == "Emenda de Bancada"


def test_api_para_quando_bloqueada():
    from coletor.api import APIBloqueada

    class Resp:
        status_code = 200
        text = "<html>bloqueado</html>"

        def json(self):
            raise ValueError("Expecting value")

    class Sessao:
        headers = {}

        def get(self, *a, **k):
            return Resp()

    api = PortalTransparencia(chave="x" * 32, sessao=Sessao(), dormir=lambda s: None)
    with pytest.raises(APIBloqueada):
        api.get("despesas/documentos-por-favorecido", codigoPessoa="1")


def test_municipios_ibge_fora_do_ar_usa_banco(tmp_path, monkeypatch):
    """IBGE com timeout (como nas coletas de 22 e 23/10/2026): segue com os municípios já salvos."""
    from coletor import banco
    con = banco.conectar(tmp_path / "v.db")
    banco.upsert(con, "municipios", [{"codigo_ibge": "4105003", "nome": "Céu Azul", "uf": "PR", "populacao": 11000}])
    banco.set_meta(con, "regiao", "meso:4106")

    def fora(regiao):
        raise TimeoutError("Connection to servicodados.ibge.gov.br timed out")
    monkeypatch.setattr(coletar.ibge, "municipios", fora)
    indice = coletar.coletar_municipios(con, "meso:4106")
    assert list(indice.values()) == ["4105003"]
    assert con.execute("SELECT populacao FROM municipios").fetchone()[0] == 11000

    # banco vazio: não há como seguir, o erro sobe
    vazio = banco.conectar(tmp_path / "vazio.db")
    with pytest.raises(TimeoutError):
        coletar.coletar_municipios(vazio, "meso:4106")


def test_populacao_fora_do_ar_mantem_a_salva(tmp_path, monkeypatch):
    from coletor import banco
    con = banco.conectar(tmp_path / "v.db")
    banco.upsert(con, "municipios", [{"codigo_ibge": "4105003", "nome": "Céu Azul", "uf": "PR", "populacao": 11000}])
    monkeypatch.setattr(coletar.ibge, "municipios", lambda r: [{"codigo_ibge": "4105003", "nome": "Céu Azul", "uf": "PR"}])

    def fora(c):
        raise TimeoutError("sidra")
    monkeypatch.setattr(coletar.ibge, "populacao_censo2022", fora)
    coletar.coletar_municipios(con, "meso:4106")
    assert con.execute("SELECT populacao FROM municipios").fetchone()[0] == 11000
