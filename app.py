"""Verba Oeste — para onde vai o dinheiro federal no Oeste do Paraná.

Fonte: API do Portal da Transparência (CGU) + IBGE. Rodar: streamlit run app.py
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from coletor import banco
from painel import consultas as Q

st.set_page_config(page_title="Verba Oeste · dinheiro federal no Oeste do PR", page_icon="🔎", layout="wide")

AZUL, LARANJA, AZUL_CLARO = "#3987e5", "#d95926", "#2c4f80"
FUNDO = "#0b1020"
st.markdown("""<style>
.block-container{padding-top:1.6rem;max-width:1280px}
[data-testid="stMetricValue"]{font-size:1.9rem;font-weight:700}
[data-testid="stMetric"]{background:rgba(255,255,255,.04);border:1px solid rgba(120,150,255,.18);border-radius:14px;
  padding:14px 18px;backdrop-filter:blur(8px);box-shadow:0 0 24px -12px rgba(57,135,229,.6)}
.aviso-demo{background:rgba(217,89,38,.12);border:1px solid rgba(217,89,38,.5);color:#ffd2bd;border-radius:10px;padding:.6rem .9rem;margin-bottom:.8rem}
.fonte{font-size:.8rem;opacity:.7}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------ dados
@st.cache_resource
def conexao():
    real = banco.CAMINHO_PADRAO
    caminho = real if real.exists() else banco.CAMINHO_DEMO
    if not caminho.exists():
        from dados import gerar_demo
        gerar_demo.gerar()
    banco.conectar(caminho).close()   # garante tabelas novas em bancos antigos
    return Q.abrir(caminho)


con = conexao()
META = Q.meta(con)
DEMO = META.get("demo") == "1"
MUN = Q.municipios(con)
ANOS = Q.anos_disponiveis(con)


def fig_base(fig: go.Figure, altura: int = 420) -> go.Figure:
    fig.update_layout(height=altura, margin=dict(l=8, r=80, t=8, b=8), plot_bgcolor="rgba(0,0,0,0)",
                      paper_bgcolor="rgba(0,0,0,0)", bargap=0.28, legend=dict(orientation="h", y=1.08, x=0, traceorder="normal"),
                      hoverlabel=dict(bgcolor="#151c30", bordercolor="#3a4670", font_size=13, font_color="#e6e9f2"), font=dict(size=13))
    fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,.18)", zeroline=False)
    fig.update_yaxes(showgrid=False)
    return fig


def barras_h(rot, val, txt, cor=AZUL, altura=None, hover=None):
    n = len(rot)
    fig = go.Figure(go.Bar(y=rot, x=val, orientation="h", marker=dict(color=cor, cornerradius=4),
                           text=txt, textposition="outside", cliponaxis=False,
                           hovertext=hover or txt, hovertemplate="<b>%{y}</b><br>%{hovertext}<extra></extra>"))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(showticklabels=False)
    return fig_base(fig, altura or max(260, 34 * n + 40))


# ------------------------------------------------------------------ cabeçalho e filtros
st.title("🔎 Verba Oeste")
st.markdown("**Para onde vai o dinheiro federal no Oeste do Paraná** — emendas parlamentares e convênios por "
            "município, com dados oficiais do Portal da Transparência.")
if DEMO:
    st.markdown("<div class='aviso-demo'>⚠️ <b>Dados fictícios de demonstração.</b> Os valores, autores e convênios "
                "abaixo são inventados para mostrar o painel. Com a chave da API, o coletor substitui tudo pelos "
                "dados oficiais.</div>", unsafe_allow_html=True)

f1, f2, f3 = st.columns([1.2, 2.6, 1.2])
padrao = [a for a in ANOS if a >= max(ANOS) - 2] if ANOS else []
anos = f1.multiselect("Ano", sorted(ANOS, reverse=True), default=sorted(padrao, reverse=True), placeholder="Todos os anos")
nomes = dict(zip(MUN["codigo_ibge"], MUN["nome"]))
sel = f2.multiselect("Municípios", list(nomes), format_func=nomes.get, placeholder="Todos os municípios da região")
medida = f3.radio("Comparar por", ["Valor total", "Por habitante"], horizontal=True)

em = Q.emendas(con, anos, sel)
cv = Q.convenios(con, anos, sel)
mun = MUN[MUN["codigo_ibge"].isin(sel)] if sel else MUN
rk = Q.ranking_municipios(em, cv, mun)
alertas = Q.alertas_convenios(cv)

k = st.columns(4)
k[0].metric("Emendas pagas", Q.brl(em["pago"].sum(), curto=True), help="Valor efetivamente pago (ordens bancárias) "
            "de emendas parlamentares a prefeituras e fundos dos municípios selecionados.")
k[1].metric("Emendas que chegaram", f"{em['codigo'].nunique()}",
            help="Número de emendas parlamentares com pagamento a algum município filtrado (inclui as 'emendas Pix').")
k[2].metric("Convênios — valor liberado", Q.brl(cv["valor_liberado"].sum(), curto=True),
            help="Repasses já liberados em convênios e contratos de repasse com os municípios.")
k[3].metric("Convênios em alerta", len(alertas), help="Vigência encerrada com menos de 50% do valor liberado.")

aba1, aba2, aba3, aba4, aba5 = st.tabs(["📊 Visão geral", "🏛️ Emendas", "🤝 Convênios", "📍 Município", "ℹ️ Sobre os dados"])

# ------------------------------------------------------------------ visão geral
with aba1:
    col_val = "total" if medida == "Valor total" else "por_habitante"
    d = rk[rk[col_val].notna()].sort_values(col_val, ascending=False).head(20)
    st.subheader("Ranking dos municípios" + (" por habitante" if col_val == "por_habitante" else ""))
    st.caption("Emendas pagas + convênios liberados no período filtrado." +
               (" Dividido pela população do Censo 2022 — é a comparação justa entre cidades grandes e pequenas."
                if col_val == "por_habitante" else ""))
    if d.empty:
        st.info("Sem dados para os filtros escolhidos.")
    else:
        if col_val == "total":
            fig = go.Figure()
            fig.add_bar(y=d["nome"], x=d["emendas_pagas"], name="Emendas pagas", orientation="h",
                        marker=dict(color=AZUL, line=dict(width=2, color=FUNDO)),
                        hovertext=[Q.brl(v) for v in d["emendas_pagas"]],
                        hovertemplate="<b>%{y}</b><br>Emendas pagas: %{hovertext}<extra></extra>")
            fig.add_bar(y=d["nome"], x=d["convenios_liberados"], name="Convênios liberados", orientation="h",
                        marker=dict(color=LARANJA, line=dict(width=2, color=FUNDO)),
                        hovertext=[Q.brl(v) for v in d["convenios_liberados"]],
                        hovertemplate="<b>%{y}</b><br>Convênios liberados: %{hovertext}<extra></extra>",
                        text=[Q.brl(v, True) for v in d["total"]], textposition="outside", cliponaxis=False)
            fig.update_layout(barmode="stack")
            fig.update_yaxes(autorange="reversed")
            fig.update_xaxes(showticklabels=False)
            st.plotly_chart(fig_base(fig, max(300, 32 * len(d) + 60)), use_container_width=True)
        else:
            st.plotly_chart(barras_h(d["nome"], d["por_habitante"],
                                     [Q.brl(v) for v in d["por_habitante"]],
                                     hover=[f"{Q.brl(v)} por habitante · total {Q.brl(t, True)} · "
                                            f"{int(p):,} hab.".replace(",", ".")
                                            for v, t, p in zip(d["por_habitante"], d["total"], d["populacao"])]),
                            use_container_width=True)
    with st.expander("Ver tabela"):
        tab = rk[["nome", "populacao", "emendas_pagas", "convenios_liberados", "total", "por_habitante"]].rename(
            columns={"nome": "Município", "populacao": "População", "emendas_pagas": "Emendas pagas (R$)",
                     "convenios_liberados": "Convênios liberados (R$)", "total": "Total (R$)",
                     "por_habitante": "R$ por habitante"})
        st.dataframe(tab, hide_index=True, use_container_width=True, column_config={
            c: st.column_config.NumberColumn(format="localized") for c in tab.columns[2:]})
        st.download_button("Baixar CSV", tab.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                           "ranking_municipios.csv", "text/csv")

# ------------------------------------------------------------------ emendas
with aba2:
    if em.empty:
        st.info("Nenhuma emenda para os filtros escolhidos.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Quem mais destinou")
            st.caption("Autores das emendas pagas aos municípios filtrados.")
            a = em[em["autor"] != ""].groupby("autor", as_index=False).agg(pago=("pago", "sum"), n=("codigo", "nunique"))
            a = a.sort_values("pago", ascending=False).head(12)
            st.plotly_chart(barras_h(a["autor"].str.title(), a["pago"], [Q.brl(v, True) for v in a["pago"]],
                                     hover=[f"{Q.brl(p)} pagos em {n} emenda(s)" for p, n in zip(a["pago"], a["n"])]),
                            use_container_width=True)
        with c2:
            st.subheader("Para quais áreas")
            st.caption("Valor pago por função de governo.")
            f = em.groupby("funcao", as_index=False)["pago"].sum().sort_values("pago", ascending=False)
            st.plotly_chart(barras_h(f["funcao"], f["pago"], [Q.brl(v, True) for v in f["pago"]]),
                            use_container_width=True)

        st.subheader("Pago por ano e tipo de emenda")
        st.caption("As transferências especiais (\"emendas Pix\") caem direto no caixa da prefeitura, sem convênio.")
        y = Q.emendas(con, None, sel)
        y["Tipo"] = y["tipo"].map(Q.tipo_curto)
        ordem = ["Transferência especial (Pix)", "Emenda individual", "Emenda de bancada", "Emenda de comissão", "Outras"]
        cores = ["#3987e5", "#d95926", "#199e70", "#c98500", "#8a8fa3"]
        g = y.groupby(["ano", "Tipo"], as_index=False)["pago"].sum()
        fig = go.Figure()
        for tipo, cor in zip(ordem, cores):
            d = g[g["Tipo"] == tipo]
            if d.empty:
                continue
            fig.add_bar(x=d["ano"].astype(str), y=d["pago"], name=tipo,
                        marker=dict(color=cor, line=dict(width=2, color=FUNDO)),
                        hovertext=[Q.brl(v) for v in d["pago"]],
                        hovertemplate="%{x} · " + tipo + ": %{hovertext}<extra></extra>")
        tot = g.groupby("ano", as_index=False)["pago"].sum()
        fig.add_scatter(x=tot["ano"].astype(str), y=tot["pago"], mode="text", text=[Q.brl(v, True) for v in tot["pago"]],
                        textposition="top center", showlegend=False, hoverinfo="skip")
        fig.update_layout(barmode="stack")
        fig.update_yaxes(showticklabels=False, showgrid=True, gridcolor="rgba(128,128,128,.18)")
        fig.update_xaxes(showgrid=False, type="category")
        st.plotly_chart(fig_base(fig, 360), use_container_width=True)

        st.subheader("Todas as emendas")
        busca = st.text_input("Buscar autor, município ou área", key="busca_em")
        t = em.copy()
        if busca:
            m = t[["autor", "municipio", "funcao"]].apply(lambda s: s.str.contains(busca, case=False, na=False)).any(axis=1)
            t = t[m]
        t["tipo"] = t["tipo"].map(Q.tipo_curto)
        t = t.sort_values("pago", ascending=False)[["ano", "municipio", "favorecido", "autor", "tipo", "funcao", "pago"]]
        t.columns = ["Ano", "Município", "Quem recebeu", "Autor", "Tipo", "Área", "Pago (R$)"]
        st.dataframe(t, hide_index=True, use_container_width=True, height=360, column_config={
            "Pago (R$)": st.column_config.NumberColumn(format="localized"),
            "Ano": st.column_config.NumberColumn(format="%d")})
        st.download_button("Baixar CSV", t.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                           "emendas.csv", "text/csv")

# ------------------------------------------------------------------ convênios
with aba3:
    if cv.empty:
        st.info("Nenhum convênio para os filtros escolhidos.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Por órgão federal")
            o = cv.groupby("orgao", as_index=False)["valor"].sum().sort_values("valor", ascending=False).head(10)
            st.plotly_chart(barras_h(o["orgao"], o["valor"], [Q.brl(v, True) for v in o["valor"]], cor=LARANJA),
                            use_container_width=True)
        with c2:
            st.subheader("Situação")
            s = cv.groupby("situacao", as_index=False).agg(qtd=("id", "count"), valor=("valor", "sum")).sort_values("valor", ascending=False)
            st.plotly_chart(barras_h(s["situacao"], s["valor"], [f"{Q.brl(v, True)} · {q}" for v, q in zip(s["valor"], s["qtd"])],
                                     cor=LARANJA), use_container_width=True)
        st.subheader(f"⚠️ Convênios em alerta ({len(alertas)})")
        st.caption("Vigência já encerrada e menos de 50% do valor liberado. Não é prova de irregularidade: pode ser "
                   "prorrogação ainda não registrada, obra cancelada ou atraso — mas merece uma pergunta.")
        if alertas.empty:
            st.success("Nenhum convênio nessa situação nos filtros atuais.")
        else:
            a = alertas[["municipio", "objeto", "orgao", "valor", "valor_liberado", "pct_liberado", "fim_vigencia"]].copy()
            a["fim_vigencia"] = pd.to_datetime(a["fim_vigencia"]).dt.strftime("%d/%m/%Y")
            a.columns = ["Município", "Objeto", "Órgão", "Valor (R$)", "Liberado (R$)", "% liberado", "Fim da vigência"]
            st.dataframe(a, hide_index=True, use_container_width=True, column_config={
                "Valor (R$)": st.column_config.NumberColumn(format="localized"),
                "Liberado (R$)": st.column_config.NumberColumn(format="localized"),
                "% liberado": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)})
        st.subheader("Todos os convênios")
        t = cv.sort_values("valor", ascending=False)[["ano", "municipio", "objeto", "orgao", "situacao", "valor", "valor_liberado"]]
        t.columns = ["Ano", "Município", "Objeto", "Órgão", "Situação", "Valor (R$)", "Liberado (R$)"]
        st.dataframe(t, hide_index=True, use_container_width=True, height=340, column_config={
            "Valor (R$)": st.column_config.NumberColumn(format="localized"),
            "Liberado (R$)": st.column_config.NumberColumn(format="localized"),
            "Ano": st.column_config.NumberColumn(format="%d")})
        st.download_button("Baixar CSV", t.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                           "convenios.csv", "text/csv")

# ------------------------------------------------------------------ município
with aba4:
    cod = st.selectbox("Escolha um município", list(nomes), format_func=nomes.get,
                       index=list(nomes.values()).index("Cascavel") if "Cascavel" in nomes.values() else 0)
    rk_all = Q.ranking_municipios(Q.emendas(con, anos), Q.convenios(con, anos), MUN)
    linha = rk_all[rk_all["municipio_codigo"] == cod].iloc[0]
    pos = int((rk_all["total"] > linha["total"]).sum()) + 1
    media_hab = rk_all["por_habitante"].median()
    c = st.columns(4)
    c[0].metric("Total recebido", Q.brl(linha["total"], True))
    c[1].metric("Posição na região", f"{pos}º de {len(rk_all)}")
    if pd.notna(linha["por_habitante"]):
        dif = linha["por_habitante"] / media_hab - 1 if media_hab else 0
        c[2].metric("Por habitante", Q.brl(linha["por_habitante"]),
                    f"{dif:+.0%} vs. mediana da região".replace(".", ","), delta_color="off")
    c[3].metric("Emendas / convênios", f"{int(linha['qtd_emendas'])} / {int(linha['qtd_convenios'])}")
    em_m = Q.emendas(con, anos, [cod])
    cv_m = Q.convenios(con, anos, [cod])
    l, r = st.columns(2)
    with l:
        st.markdown("**Emendas**")
        st.dataframe(em_m.sort_values("pago", ascending=False)[["ano", "autor", "funcao", "pago"]].rename(
            columns={"ano": "Ano", "autor": "Autor", "funcao": "Área", "pago": "Pago (R$)"}),
            hide_index=True, use_container_width=True,
            column_config={"Pago (R$)": st.column_config.NumberColumn(format="localized"),
                           "Ano": st.column_config.NumberColumn(format="%d")})
    with r:
        st.markdown("**Convênios**")
        st.dataframe(cv_m.sort_values("valor", ascending=False)[["objeto", "situacao", "valor", "valor_liberado"]].rename(
            columns={"objeto": "Objeto", "situacao": "Situação", "valor": "Valor (R$)", "valor_liberado": "Liberado (R$)"}),
            hide_index=True, use_container_width=True,
            column_config={"Valor (R$)": st.column_config.NumberColumn(format="localized"),
                           "Liberado (R$)": st.column_config.NumberColumn(format="localized")})

# ------------------------------------------------------------------ sobre
with aba5:
    st.markdown(f"""
**Fontes**
- [API do Portal da Transparência](https://api.portaldatransparencia.gov.br/swagger-ui/index.html) (Controladoria-Geral da União): emendas parlamentares e convênios.
- [IBGE](https://servicodados.ibge.gov.br/api/docs): lista de municípios da mesorregião Oeste Paranaense e população do Censo 2022.

**Como os dados chegam aqui**
1. Um coletor em Python consulta a API todos os dias (GitHub Actions), respeitando o limite de consultas por minuto da API.
2. Os dados são limpos (valores em texto viram números, nomes de cidades são casados com o código do IBGE) e gravados num banco SQLite.
3. O painel lê só o banco — por isso abre rápido e não depende da API estar no ar.

**Cuidados de leitura**
- A cidade de cada emenda vem do **pagamento** (quem recebeu a ordem bancária: prefeitura ou fundo municipal). Assim entram as "emendas Pix", cujo destino oficial aparece só como "Paraná (UF)".
- Pagamentos a entidades privadas (hospitais, associações) contam para a cidade quando o nome indica o município.
- O alerta de convênio é um sinal para investigar, não uma acusação.

**Atualização:** {META.get('atualizado_em', '—')} · Região: {META.get('regiao', '—')}
""")
    st.markdown("<p class='fonte'>Projeto de portfólio de João Carlos Moraes · "
                "<a href='https://jcmoraes-sistemas.netlify.app'>jcmoraes-sistemas.netlify.app</a></p>",
                unsafe_allow_html=True)
