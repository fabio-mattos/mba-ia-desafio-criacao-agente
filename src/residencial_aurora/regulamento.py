"""Busca no regulamento por capitulo, sem carregar o documento inteiro.

Garantia 4: o regulamento e longo, e nenhum evento da sessao pode conter
trechos de capitulos que nao tem a ver com a pergunta. Em vez de dar o
arquivo inteiro (ou o proprio LLM) o poder de decidir o que "faz parte da
resposta", o codigo faz uma busca lexical determinística e devolve so o
texto do capitulo mais relevante. E esse texto, sozinho, que vira o retorno
da tool `consultar_regulamento` (agents/tools.py) e portanto o unico trecho
do regulamento que pode aparecer nos eventos da sessao.

Pontuacao: cada termo da pergunta pesa pelo IDF (um termo presente em quase
todos os capitulos, como "apartamento", quase nao conta), com frequencia
amortecida por log, bonus para termos do titulo, radical de 6 letras e um
pequeno dicionario de sinonimos ("cachorro" -> "cao").
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from .config import REGULAMENTO_MD

_STOPWORDS = {
    "a", "as", "o", "os", "de", "da", "do", "das", "dos", "e", "em", "no",
    "na", "nos", "nas", "um", "uma", "uns", "umas", "ao", "aos", "que",
    "para", "por", "com", "se", "sua", "seu", "suas", "seus", "ate", "que",
    "quais", "qual", "quando", "onde", "como", "quanto", "quanto",
    "sobre", "ou", "eu", "voce", "meu", "minha", "sao", "ser", "esta",
    "este", "isso", "pode", "posso", "gostaria", "queria", "quero",
}

# Termos do dia a dia que o regulamento escreve de outro jeito.
_SINONIMOS = {
    "cachorro": "cao", "cachorros": "cao", "caes": "cao", "cadela": "cao",
    "gato": "animal", "gatos": "animal", "pet": "animal", "pets": "animal",
    "bicho": "animal", "bichos": "animal", "animais": "animal",
    "barulho": "ruido", "carro": "veiculo", "carros": "veiculo",
    "moto": "veiculo", "reforma": "obra", "reformas": "obra",
    "festa": "festas", "lixeira": "lixo", "multa": "multas",
}

_PESO_TITULO = 5

_CHAPTER_RE = re.compile(r"^##\s+(Cap[íi]tulo.*)$", re.MULTILINE)


@dataclass(frozen=True)
class Capitulo:
    titulo: str
    texto: str


def _normalizar(texto: str) -> list[str]:
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    tokens = re.findall(r"[a-z0-9]+", sem_acento)
    termos = []
    for t in tokens:
        if t in _STOPWORDS or len(t) <= 1:
            continue
        t = _SINONIMOS.get(t, t)
        # Radical simples: "reciclavel", "reciclaveis" e "reciclagem" viram "recicl".
        termos.append(t[:6])
    return termos


@lru_cache(maxsize=1)
def _capitulos() -> list[Capitulo]:
    conteudo = REGULAMENTO_MD.read_text(encoding="utf-8")
    matches = list(_CHAPTER_RE.finditer(conteudo))
    capitulos = []
    for i, match in enumerate(matches):
        inicio = match.start()
        fim = matches[i + 1].start() if i + 1 < len(matches) else len(conteudo)
        bloco = conteudo[inicio:fim].strip()
        capitulos.append(Capitulo(titulo=match.group(1).strip(), texto=bloco))
    return capitulos


@lru_cache(maxsize=1)
def _indice() -> tuple[list[Counter[str]], dict[str, float]]:
    # Termos do titulo contam como varias ocorrencias: o titulo resume o capitulo.
    frequencias = [
        Counter(_normalizar(c.texto)) + Counter(_normalizar(c.titulo) * _PESO_TITULO)
        for c in _capitulos()
    ]
    total = len(frequencias)
    idf = {}
    for termo in set().union(*frequencias):
        presentes = sum(1 for f in frequencias if termo in f)
        idf[termo] = math.log((total + 1) / presentes)
    return frequencias, idf


def buscar(pergunta: str) -> Capitulo:
    """Retorna o capitulo mais relevante para a pergunta (maior pontuacao IDF)."""
    termos_pergunta = set(_normalizar(pergunta))
    frequencias, idf = _indice()
    capitulos = _capitulos()
    melhor = capitulos[0]
    melhor_pontuacao = -1.0
    for capitulo, freq in zip(capitulos, frequencias):
        pontuacao = sum(
            idf[t] * math.log1p(freq[t]) for t in termos_pergunta if t in freq
        )
        if pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor = capitulo
    return melhor
