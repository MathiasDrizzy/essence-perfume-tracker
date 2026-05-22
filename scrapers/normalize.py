"""Normaliza títulos crudos de productos de perfume → atributos canónicos.

Cada retailer escribe los títulos de forma distinta:
- "Armaf Odyssey Homme White Edición EDP 100ml" (silkperfumes)
- "Odyssey Homme White Edition EDP 100 ML for Men - Armaf" (multimarcasperfumes)
- "Perfume Armaf Odyssey Homme White Edp 200ml Hombre" (mercadolibre)

Salida: dict con brand, name, concentration, volume_ml, gender, canonical_slug.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# Concentraciones reconocidas. Orden importa: las más específicas primero.
# OJO: "edicion"/"edición" significan "edition" (parte del nombre), NO Eau de Parfum.
CONCENTRATIONS = [
    ("PARFUM", r"\b(extrait\s+de\s+)?parfum\b"),
    ("EDP", r"\b(e\.?d\.?p\.?|eau\s+de\s+parfum)\b"),
    ("EDT", r"\b(e\.?d\.?t\.?|eau\s+de\s+toilette)\b"),
    ("EDC", r"\b(e\.?d\.?c\.?|eau\s+de\s+cologne)\b"),
]

# Marcas conocidas (lowercased keys). Se expande con el tiempo.
KNOWN_BRANDS = {
    "armaf", "lattafa", "afnan", "rasasi", "ajmal", "khadlaj", "dolce & gabbana",
    "dolce gabbana", "d&g", "dior", "chanel", "calvin klein", "ck", "carolina herrera",
    "ch", "paco rabanne", "rabanne", "yves saint laurent", "ysl", "saint laurent",
    "tom ford", "jean paul gaultier", "jpg", "versace", "azzaro", "hugo boss", "boss",
    "lacoste", "ralph lauren", "ralph", "polo", "burberry", "givenchy", "guerlain",
    "kenzo", "issey miyake", "issey", "bvlgari", "bulgari", "moschino", "viktor & rolf",
    "marc jacobs", "tommy hilfiger", "tommy", "abercrombie", "hollister", "guess",
    "victoria's secret", "victoria secret", "victorias secret", "ariana grande",
    "britney spears", "katy perry", "jennifer lopez", "j lo", "jlo", "antonio banderas",
    "banderas", "axe", "old spice", "nautica", "playboy", "adidas", "puma", "diesel",
    "lancome", "lancôme", "estée lauder", "estee lauder", "elizabeth arden", "clinique",
    "shiseido", "narciso rodriguez", "narciso", "by kilian", "kilian", "creed",
    "maison francis kurkdjian", "mfk", "kurkdjian", "amouage", "memo", "xerjoff",
    "parfums de marly", "marly", "roja", "clive christian", "tiziana terenzi",
    "mancera", "montale", "le labo", "diptyque", "byredo", "comme des garcons",
    "comme des garçons", "maison margiela", "margiela", "replica", "moschino",
    "michael kors", "kors", "perry ellis", "ellis", "cuba", "lomani", "swiss arabian",
    "al haramain", "haramain", "nasamat", "fragrance world", "milestone",
    "emporio armani", "armani", "giorgio armani", "bond no 9", "bond no. 9",
}

# Géneros: "homme"/"femme" NO van aquí porque son parte de nombres de perfume
# (ej: "Pour Homme", "Odyssey Homme White"). Solo señales explícitas en es/en.
# Las versiones francesas se detectan con "pour homme"/"pour femme" compuestas.
GENDER_HINTS = {
    "hombre": "Hombre", "for men": "Hombre", "pour homme": "Hombre",
    "masculino": "Hombre", "caballero": "Hombre",
    "mujer": "Mujer", "for women": "Mujer", "pour femme": "Mujer",
    "femenino": "Mujer", "dama": "Mujer",
    "unisex": "Unisex",
}

# Patrones de ruido que se eliminan ANTES de detectar marca (matan claims rivales).
# Estos casos son clones / réplicas donde el título menciona la marca original
# pero el producto es de OTRA marca. Ej:
#   "RISALA PURE OMBRE EDP 100ML UNISEX (XERJOFF ERBA PURA)" → marca real Risala
#   "Odyssey Homme White Edition Armaf - Inspirado en Stronger With You"
PRE_BRAND_NOISE = [
    r"\binspirado\s+en\b.*$",
    r"\binspired\s+by\b.*$",
    r"\binspired\s+in\b.*$",
    r"\bclon\s+(?:de\s+|del\s+)?.*$",
    r"\breplica\s+(?:de\s+)?.*$",
    r"\bsimilar\s+a\b.*$",
    # Paréntesis con marca alternativa al final del título (común en clones Ripley)
    r"\([^()]*\)\s*$",
]

# Patrones de ruido en el nombre final (corren DESPUÉS de extraer marca/conc/vol/género)
NOISE_WORDS = [
    r"\bperfume\b", r"\boriginal\b", r"\btester\b", r"\bprobador\b", r"\bnuevo\b",
    r"\bsellado\b", r"\bsealed\b", r"\benvio\s+gratis\b", r"\benvío\s+gratis\b",
    r"\bset\b\s*\(.*?\)", r"\(\s*tester\s*\)", r"\(\s*probador\s*\)",
    r"\bspray\b", r"\bfor\b",
]


@dataclass(frozen=True)
class NormalizedProduct:
    brand: str
    name: str
    concentration: str | None
    volume_ml: int
    gender: str | None
    canonical_slug: str


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _slugify(s: str) -> str:
    s = _strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def _extract_volume(title: str) -> int | None:
    """Encuentra '100ml', '100 ML', '100 ml', '3.4 oz' (→ ~100ml)."""
    m = re.search(r"(\d{2,4})\s*(?:ml|m\.l\.|millilit)", title, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*oz\b", title, re.IGNORECASE)
    if m:
        return round(float(m.group(1)) * 29.5735)
    return None


def _extract_concentration(title: str) -> str | None:
    for code, pattern in CONCENTRATIONS:
        if re.search(pattern, title, re.IGNORECASE):
            return code
    return None


def _extract_gender(title: str) -> str | None:
    t = " " + title.lower() + " "
    for hint, gender in GENDER_HINTS.items():
        if f" {hint} " in t or t.endswith(f" {hint}"):
            return gender
    return None


def _extract_brand(title: str) -> str | None:
    """Match marca conocida en cualquier posición del título."""
    t = _strip_accents(title).lower()
    # Ordena por longitud descendente para preferir "dolce & gabbana" sobre "dolce"
    for brand in sorted(KNOWN_BRANDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(brand)}\b", t):
            return brand.title().replace("&", "&")
    return None


def _clean_name(title: str, brand: str | None, concentration: str | None, volume: int | None) -> str:
    name = title
    # Remueve marca
    if brand:
        name = re.sub(rf"\b{re.escape(brand)}\b", "", name, flags=re.IGNORECASE)
    # Remueve concentración (texto completo, no solo el código)
    for _, pattern in CONCENTRATIONS:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE)
    # Remueve volumen (acepta separación opcional: "100ml", "100 ml", "100ML")
    if volume:
        name = re.sub(rf"\b{volume}\s*(?:ml|m\.l\.|oz)\b", "", name, flags=re.IGNORECASE)
    # Remueve género (incluye "for men"/"for women" compuestos antes de palabras sueltas)
    for hint in sorted(GENDER_HINTS, key=len, reverse=True):
        name = re.sub(rf"\b{re.escape(hint)}\b", "", name, flags=re.IGNORECASE)
    # Remueve ruido (incluye "for" suelto que sobrevive a "for men")
    for pattern in NOISE_WORDS:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE)
    # Limpia paréntesis vacíos y separadores colgando
    name = re.sub(r"\(\s*\)", "", name)
    name = re.sub(r"[\-\|·–—]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" -,.|()")
    return name


def normalize(title: str, fallback_brand: str | None = None) -> NormalizedProduct | None:
    """Devuelve None si no se pudo extraer marca o volumen (datos insuficientes)."""
    title = title.strip()

    # Pre-clean: matar "inspirado en X" antes de detectar marca para no confundir
    pre_cleaned = title
    for pattern in PRE_BRAND_NOISE:
        pre_cleaned = re.sub(pattern, "", pre_cleaned, flags=re.IGNORECASE)

    volume = _extract_volume(pre_cleaned)
    if volume is None:
        return None

    brand = _extract_brand(pre_cleaned) or fallback_brand
    if not brand:
        return None

    concentration = _extract_concentration(pre_cleaned)
    gender = _extract_gender(pre_cleaned)
    name = _clean_name(pre_cleaned, brand, concentration, volume)
    if not name:
        return None

    slug = _slugify(f"{brand} {name} {concentration or ''} {volume}")
    return NormalizedProduct(
        brand=brand.strip(),
        name=name.strip(),
        concentration=concentration,
        volume_ml=volume,
        gender=gender,
        canonical_slug=slug,
    )
