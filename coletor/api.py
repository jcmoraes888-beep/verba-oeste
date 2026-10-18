"""Cliente da API do Portal da Transparência (CGU) com limite de taxa e retentativas.

Documentação: https://api.portaldatransparencia.gov.br/swagger-ui/index.html
A chave é gratuita (cadastro com gov.br) e vai no cabeçalho `chave-api-dados`.
Limites oficiais: 400 req/min (06h–24h), 700 req/min (00h–06h) e 180 req/min nos endpoints
"restritos" (ex.: despesas/documentos-por-favorecido). Usamos 120 req/min em TUDO para ter folga:
estourar o limite suspende a chave por 8 horas. Se a API parar de responder JSON (sinal de
bloqueio), a coleta para na hora em vez de insistir.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Iterator

import requests

BASE = "https://api.portaldatransparencia.gov.br/api-de-dados"
log = logging.getLogger(__name__)


class ErroAPI(Exception):
    pass


class APIBloqueada(ErroAPI):
    """Chave recusada, suspensa ou resposta que não é JSON: parar a coleta inteira."""


ARQUIVO_CHAVE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chave_api.txt")


def ler_chave_arquivo() -> str:
    """Para uso local: a chave pode ficar no arquivo chave_api.txt (ignorado pelo git)."""
    try:
        with open(ARQUIVO_CHAVE, encoding="utf-8-sig") as f:
            texto = f.read()
    except OSError:
        return ""
    # tolera texto colado junto (aspas, colchetes, "chave:" etc.): pega o maior trecho alfanumérico
    trechos = re.findall(r"[A-Za-z0-9]{20,}", texto)
    return max(trechos, key=len) if trechos else texto.strip()


class PortalTransparencia:
    def __init__(self, chave: str | None = None, por_minuto: int = 120, sessao: requests.Session | None = None,
                 dormir=time.sleep):
        env = os.environ.get("PORTAL_API_KEY", "")
        if "COLE_SUA" in env.upper():   # sobra do exemplo do README
            env = ""
        self.chave = chave or env or ler_chave_arquivo()
        if not self.chave:
            raise ErroAPI("Chave não encontrada: cole a chave no arquivo chave_api.txt (na pasta do projeto) "
                          "ou defina PORTAL_API_KEY.")
        self.intervalo = 60.0 / por_minuto
        self.sessao = sessao or requests.Session()
        self.sessao.headers.update({"chave-api-dados": self.chave, "Accept": "application/json",
                                    "User-Agent": "verba-oeste (projeto de portfólio)"})
        self._ultima = 0.0
        self._dormir = dormir
        self.requisicoes = 0

    def _esperar_vez(self):
        falta = self.intervalo - (time.monotonic() - self._ultima)
        if falta > 0:
            self._dormir(falta)
        self._ultima = time.monotonic()

    def get(self, caminho: str, **params) -> list | dict:
        url = f"{BASE}/{caminho.lstrip('/')}"
        for tentativa in range(5):
            self._esperar_vez()
            self.requisicoes += 1
            try:
                r = self.sessao.get(url, params={k: v for k, v in params.items() if v not in (None, "")}, timeout=60)
            except requests.RequestException as e:
                log.warning("Falha de rede (%s), tentativa %d", e, tentativa + 1)
                self._dormir(5 * (tentativa + 1))
                continue
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    raise APIBloqueada(f"A API respondeu algo que não é JSON em {caminho} (provável bloqueio "
                                       f"por excesso de requisições). Coleta interrompida: {r.text[:120]!r}")
            if r.status_code in (429, 500, 502, 503, 504):
                espera = 30 if r.status_code == 429 else 5 * (tentativa + 1)
                log.warning("HTTP %s em %s — aguardando %ss", r.status_code, caminho, espera)
                self._dormir(espera)
                continue
            if r.status_code in (401, 403):
                raise APIBloqueada("Chave da API recusada ou suspensa (HTTP %s). Confira PORTAL_API_KEY." % r.status_code)
            raise ErroAPI(f"HTTP {r.status_code} em {caminho}: {r.text[:200]}")
        raise ErroAPI(f"Desisti após 5 tentativas em {caminho}")

    def paginas(self, caminho: str, max_paginas: int = 2000, **params) -> Iterator[dict]:
        """Percorre `pagina=1,2,…` até vir lista vazia."""
        for pagina in range(1, max_paginas + 1):
            itens = self.get(caminho, pagina=pagina, **params)
            if not itens:
                return
            yield from itens
        log.warning("Parei em %d páginas de %s (limite de segurança)", max_paginas, caminho)

    # ------------------------------------------------------------- endpoints usados
    def emendas(self, ano: int) -> Iterator[dict]:
        return self.paginas("emendas", ano=ano)

    def convenios(self, codigo_ibge: str, data_inicial: str, data_final: str) -> Iterator[dict]:
        # datas no formato DD/MM/AAAA (vigência)
        return self.paginas("convenios", codigoIBGE=codigo_ibge,
                            dataInicial=data_inicial, dataFinal=data_final)
