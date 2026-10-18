# 🔎 Verba Oeste

**Para onde vai o dinheiro federal no Oeste do Paraná.** Painel interativo com emendas parlamentares e convênios
federais destinados aos municípios da região, a partir de dados **oficiais** do Portal da Transparência (CGU) e do IBGE.

> 🇬🇧 *Interactive dashboard tracking federal parliamentary amendments and transfer agreements to municipalities in
> Western Paraná, Brazil, built on the official Transparency Portal API. Daily automated collection with GitHub
> Actions, SQLite storage and a Streamlit front end.*

## O que o painel responde

- **Quais cidades mais recebem** — em valor total e **por habitante** (Censo 2022), que é a comparação justa.
- **Quem destinou** — ranking dos autores das emendas pagas à região.
- **Para quais áreas** — saúde, educação, urbanismo, agricultura…
- **Prometido × pago** — quanto do empenhado virou pagamento, por ano.
- **Convênios em alerta** — vigência encerrada com menos de 50% liberado (sinal para investigar, não acusação).
- **Ficha de cada município** — posição na região e comparação com a mediana.

## Arquitetura

```
GitHub Actions (todo dia)
   └─ coletor/coletar.py ──► API do Portal da Transparência  (limite de 400 req/min, retentativas)
                         └─► API do IBGE (municípios da mesorregião + população Censo 2022)
        │  limpeza: valores "1.234,56" → número; "CÉU AZUL - PR" → código IBGE
        ▼
   dados/verba.db (SQLite, versionado no repositório)
        ▼
   app.py (Streamlit + Plotly) — lê só o banco: abre rápido e não depende da API estar no ar
```

| Pasta | O que tem |
|---|---|
| `coletor/api.py` | Cliente da API com controle de taxa, paginação e retentativas (429/5xx) |
| `coletor/ibge.py` | Municípios por mesorregião/UF e população |
| `coletor/normalizar.py` | Conversão tolerante dos campos da API |
| `coletor/coletar.py` | Linha de comando da coleta |
| `painel/consultas.py` | Rankings, execução, per capita e alertas |
| `dados/gerar_demo.py` | Base **fictícia** para rodar sem chave |
| `tests/` | Testes com API simulada (sem internet) |

## Rodar no computador

```bash
pip install -r requirements-dev.txt
streamlit run app.py          # sem chave, abre com dados de exemplo
```

Com a chave (cadastro gratuito em <https://portaldatransparencia.gov.br/api-de-dados>, login gov.br):

```bash
export PORTAL_API_KEY=sua_chave          # Windows PowerShell: $env:PORTAL_API_KEY="sua_chave"
python -m coletor.coletar --anos 2024 2025 2026
python -m coletor.coletar --regiao uf:41  # o Paraná inteiro
streamlit run app.py
```

## Coleta automática (GitHub Actions)

1. No repositório: **Settings → Secrets and variables → Actions → New repository secret**
   `PORTAL_API_KEY` = sua chave.
2. Aba **Actions → Coleta diária → Run workflow** para a primeira carga. Depois roda sozinho todo dia.
3. Publique no **Streamlit Community Cloud** apontando para `app.py`. A cada coleta o painel atualiza.

## Testes

```bash
python -m pytest -q
```

## Limitações conhecidas

- Emendas destinadas ao estado inteiro ou a vários municípios não entram no ranking por cidade.
- A API muda nomes de campos às vezes; `normalizar.py` aceita variações conhecidas.
- O alerta de convênio não considera prorrogações que ainda não apareceram na base.

---
Projeto de portfólio de **João Carlos Moraes** · [jcmoraes-sistemas.netlify.app](https://jcmoraes-sistemas.netlify.app)
