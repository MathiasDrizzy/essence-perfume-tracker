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

# BRAND_ALIASES: variantes (lowercase, sin acentos) → forma canónica oficial.
# Cubre: typos comunes, abreviaciones (YSL, JPG, CK), variantes con/sin espacios,
# rebrandings (Paco Rabanne → Rabanne en 2023, pero unificamos a "Paco Rabanne"
# para mantener histórico).
BRAND_ALIASES: dict[str, str] = {
    # Yves Saint Laurent
    "ysl": "Yves Saint Laurent",
    "yves saint laurent": "Yves Saint Laurent",
    "yves saint lauren": "Yves Saint Laurent",  # typo común (sin la T final)
    "yves saint-laurent": "Yves Saint Laurent",
    "saint laurent": "Yves Saint Laurent",
    # Jean Paul Gaultier
    "jpg": "Jean Paul Gaultier",
    "jean paul gaultier": "Jean Paul Gaultier",
    "jean paul gaultter": "Jean Paul Gaultier",  # typo
    "jean-paul gaultier": "Jean Paul Gaultier",
    # Calvin Klein
    "ck": "Calvin Klein",
    "calvin klein": "Calvin Klein",
    # Dolce & Gabbana
    "d&g": "Dolce & Gabbana",
    "dg": "Dolce & Gabbana",
    "dolce & gabbana": "Dolce & Gabbana",
    "dolce&gabbana": "Dolce & Gabbana",
    "dolce gabbana": "Dolce & Gabbana",
    # Carolina Herrera (Ch es ambiguo con Chanel — pero Chanel SIEMPRE se escribe
    # completo, así que "Ch" solo lo usan vendedores de CH)
    "ch": "Carolina Herrera",
    "carolina herrera": "Carolina Herrera",
    # Paco Rabanne (rebranded a Rabanne pero unificamos)
    "paco rabanne": "Paco Rabanne",
    "rabanne": "Paco Rabanne",
    # Hugo Boss
    "boss": "Hugo Boss",
    "hugo boss": "Hugo Boss",
    "hugo": "Hugo Boss",
    # Tommy Hilfiger
    "tommy hilfiger": "Tommy Hilfiger",
    "tommy hilfinger": "Tommy Hilfiger",  # typo
    "tommy": "Tommy Hilfiger",
    # Tom Ford (mantener separado de Tommy Bahama/Hilfiger)
    "tom ford": "Tom Ford",
    # Giorgio Armani
    "giorgio armani": "Giorgio Armani",
    "armani": "Giorgio Armani",
    "emporio armani": "Giorgio Armani",
    "armani prive": "Giorgio Armani",
    # Versace
    "versace": "Versace",
    # Lancôme
    "lancome": "Lancôme",
    "lancôme": "Lancôme",
    # Marcas árabes populares (variantes de casing)
    "lattafa": "Lattafa",
    "armaf": "Armaf",
    "afnan": "Afnan",
    "rasasi": "Rasasi",
    "ajmal": "Ajmal",
    "maison alhambra": "Maison Alhambra",
    "fragrance world": "Fragrance World",
    "al haramain": "Al Haramain",
    "haramain": "Al Haramain",
    "khadlaj": "Khadlaj",
    "swiss arabian": "Swiss Arabian",
    "paris corner": "Paris Corner",
    "riiffs": "Riiffs",
    "grandeur": "Grandeur",
    "nasamat": "Nasamat",
    # Otras
    "victoria's secret": "Victoria's Secret",
    "victorias secret": "Victoria's Secret",
    "victoria secret": "Victoria's Secret",
    "antonio banderas": "Antonio Banderas",
    "banderas": "Antonio Banderas",
    "ralph lauren": "Ralph Lauren",
    "ralph": "Ralph Lauren",
    "polo ralph lauren": "Ralph Lauren",
    "polo": "Ralph Lauren",
    "big pony": "Ralph Lauren",
    "big pony no. 2": "Ralph Lauren",
    "ralph": "Ralph Lauren",
    "burberry": "Burberry",
    "chanel": "Chanel",
    "dior": "Dior",
    "christian dior": "Dior",
    "givenchy": "Givenchy",
    "guerlain": "Guerlain",
    "kenzo": "Kenzo",
    "issey miyake": "Issey Miyake",
    "issey": "Issey Miyake",
    "bvlgari": "Bvlgari",
    "bulgari": "Bvlgari",
    "moschino": "Moschino",
    "viktor & rolf": "Viktor & Rolf",
    "viktor&rolf": "Viktor & Rolf",
    "marc jacobs": "Marc Jacobs",
    "guess": "Guess",
    "ariana grande": "Ariana Grande",
    "britney spears": "Britney Spears",
    "katy perry": "Katy Perry",
    "jennifer lopez": "Jennifer Lopez",
    "j lo": "Jennifer Lopez",
    "jlo": "Jennifer Lopez",
    "abercrombie & fitch": "Abercrombie & Fitch",
    "abercrombie": "Abercrombie & Fitch",
    "hollister": "Hollister",
    "axe": "Axe",
    "old spice": "Old Spice",
    "nautica": "Nautica",
    "playboy": "Playboy",
    "adidas": "Adidas",
    "puma": "Puma",
    "diesel": "Diesel",
    "estee lauder": "Estée Lauder",
    "estée lauder": "Estée Lauder",
    "narciso rodriguez": "Narciso Rodriguez",
    "narciso": "Narciso Rodriguez",
    "by kilian": "By Kilian",
    "kilian": "By Kilian",
    "creed": "Creed",
    "maison francis kurkdjian": "Maison Francis Kurkdjian",
    "mfk": "Maison Francis Kurkdjian",
    "kurkdjian": "Maison Francis Kurkdjian",
    "amouage": "Amouage",
    "memo": "Memo",
    "xerjoff": "Xerjoff",
    "parfums de marly": "Parfums de Marly",
    "marly": "Parfums de Marly",
    "roja": "Roja Parfums",
    "roja parfums": "Roja Parfums",
    "clive christian": "Clive Christian",
    "tiziana terenzi": "Tiziana Terenzi",
    "mancera": "Mancera",
    "montale": "Montale",
    "le labo": "Le Labo",
    "diptyque": "Diptyque",
    "byredo": "Byredo",
    "maison margiela": "Maison Margiela",
    "margiela": "Maison Margiela",
    "lacoste": "Lacoste",
    "azzaro": "Azzaro",
    "paco": "Paco Rabanne",
    "generico": "Genérico",
    "genérico": "Genérico",
    # Acentos: forma canónica con acento (versión genuina española)
    "adolfo dominguez": "Adolfo Domínguez",
    "adolfo domínguez": "Adolfo Domínguez",
    "bebe": "Bebé",
    "bebé": "Bebé",
    "aco": "Aco",
    "benjamin vicuna": "Benjamín Vicuña",
    "benjamin vicuña": "Benjamín Vicuña",
    "benjamín vicuna": "Benjamín Vicuña",
    "benjamín vicuña": "Benjamín Vicuña",
    "pierre cardin": "Pierre Cardin",  # nombre francés sin acento (oficial)
    "pierre cardín": "Pierre Cardin",
    "pamela diaz": "Pamela Díaz",
    "pamela díaz": "Pamela Díaz",
    # Typos específicos detectados en auditoría
    "girogio armani": "Giorgio Armani",
}


def canonicalize_brand(raw: str | None) -> str | None:
    """Devuelve la forma canónica de una marca. Maneja casing, acentos, aliases."""
    if not raw:
        return None
    # Trim + colapsar whitespace
    cleaned = re.sub(r"\s+", " ", raw.strip())
    # Lookup case-insensitive en alias table (sin acentos)
    key = _strip_accents(cleaned).lower()
    if key in BRAND_ALIASES:
        return BRAND_ALIASES[key]
    # Sin alias conocido: aplicar Title Case y devolver
    # (excepto siglas todas mayúsculas: si tiene 2-3 chars y todas mayúsculas, mantener)
    if cleaned.isupper() and len(cleaned) <= 3:
        return cleaned
    return cleaned.title().replace("'S", "'s").replace("&", "&")


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
    # Marcas clone / dupes verificadas (NO incluir nombres de productos)
    "beas", "risala", "elite risala", "dumont", "dumont paris", "milestone",
    "louis varel", "louis cardin", "designer shaik", "shaik", "al wisam",
    "al rehab", "ard al zaafaran", "ardal", "kayali", "initio",
    "initio parfums", "nishane", "boadicea", "boadicea the victorious",
    "frederic malle", "atelier des ors", "carner barcelona",
    "essential parfums", "histoires de parfums", "stephane humbert lucas",
    "ex nihilo", "thameen", "amouroud", "nasamatto", "nasamat", "orto parisi",
    "vilhelm parfumerie", "franck boclet", "matiere premiere",
    "puredistance", "lalique", "molinard", "houbigant", "caron",
    "etat libre d'orange", "francesca bianchi", "rance",
    # Más designer brands que faltaban
    "jimmy choo", "michael kors", "tory burch", "vince camuto",
    "elizabeth arden", "chloe", "chloé", "miu miu", "prada",
    "gucci", "fendi", "valentino", "salvatore ferragamo", "ferragamo",
    "trussardi", "moschino", "cacharel", "armani exchange",
    "ax armani", "kenneth cole", "perry ellis", "swiss army",
    "victorinox", "swiss arabian", "swiss",
}

# Géneros: SOLO señales que claramente NO son parte del nombre del perfume.
# - "pour homme" / "pour femme" / "for her" / "for him" SE DETECTAN pero NO se
#   strippean del nombre, porque típicamente SON el nombre ("Carolina Herrera
#   Pour Femme", "For Her by Narciso Rodriguez").
GENDER_HINTS = {
    "hombre": "Hombre", "for men": "Hombre",
    "masculino": "Hombre", "caballero": "Hombre",
    "mujer": "Mujer", "for women": "Mujer",
    "femenino": "Mujer", "dama": "Mujer",
    "unisex": "Unisex",
}

# Estos sólo se usan para DETECTAR género (en _extract_gender), pero NO se
# eliminan en _clean_name.
GENDER_HINTS_DETECT_ONLY = {
    "pour homme": "Hombre",
    "pour femme": "Mujer",
    "for him": "Hombre",
    "for her": "Mujer",
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

# Productos que NO son perfumes aunque tengan marca conocida + volumen. Se detectan
# por palabras clave en el título y se rechazan antes de insertar al catálogo.
NON_PERFUME_BLOCK = re.compile(
    r"\b(desodoran\w+|deo\s+spray|shampoo|champ[uú]|esmalte"
    r"|acondicionador|conditioner|cabello|hair\s+(?:mask|treatment|care)"
    r"|loreal\s+professionnel|loréal\s+professionnel"
    r"|gel\s+de\s+(?:ducha|baño)|shower\s+gel(?!\s*estuche)"
    r"|crema\s+(?:corporal|hidratante|de\s+manos)"
    r"|body\s+(?:lotion|cream|scrub)"
    r"|locion\s+corporal|loción\s+corporal"
    r"|alcohol\s+gel|hand\s+sanitiz)\b",
    re.IGNORECASE,
)

# Patrones de ruido en el nombre final (corren DESPUÉS de extraer marca/conc/vol/género)
NOISE_WORDS = [
    r"\bperfume\b", r"\boriginal\b", r"\btester\b", r"\bprobador\b", r"\bnuevo\b",
    r"\bsellado\b", r"\bsealed\b", r"\benvio\s+gratis\b", r"\benvío\s+gratis\b",
    r"\bset\b\s*\(.*?\)", r"\(\s*tester\s*\)", r"\(\s*probador\s*\)",
    r"\bspray\b", r"\bfor\b",
    # MercadoLibre: info del vendedor que no es parte del nombre del perfume
    r"[-–—]\s*distribuidor\s+autorizado\b.*$",
    r"\bdistribuidor\s+autorizado\b.*$",
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
    """Encuentra '100ml', '100 ML', '100 ml', '3.4 oz' (→ ~100ml).

    Fallback: si título tiene 'EDP 100' / 'EDT 50' (concentración + número sin
    'ml'), asume ml. Solo si el número es un volumen plausible (5-1000)."""
    m = re.search(r"(\d{2,4})\s*(?:ml|m\.l\.|millilit)\b", title, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)\s*oz\b", title, re.IGNORECASE)
    if m:
        return round(float(m.group(1)) * 29.5735)
    # Fallback: concentración + número (ej. "EDP 100", "EDT 50")
    m = re.search(
        r"\b(?:edp|edt|edc|parfum|cologne|colonia)\s+(\d{1,4})\b",
        title,
        re.IGNORECASE,
    )
    if m:
        v = int(m.group(1))
        if 5 <= v <= 1000:  # rango plausible para perfume
            return v
    return None


def _extract_concentration(title: str) -> str | None:
    for code, pattern in CONCENTRATIONS:
        if re.search(pattern, title, re.IGNORECASE):
            return code
    return None


def _extract_gender(title: str) -> str | None:
    t = " " + title.lower() + " "
    # Detección por hints explícitos (strippeables del nombre)
    for hint, gender in GENDER_HINTS.items():
        if f" {hint} " in t or t.endswith(f" {hint}"):
            return gender
    # Detección por hints que NO se strippean (suelen ser parte del nombre)
    for hint, gender in GENDER_HINTS_DETECT_ONLY.items():
        if f" {hint} " in t or t.endswith(f" {hint}"):
            return gender
    return None


def _extract_brand(title: str) -> str | None:
    """Match marca conocida en el título. Prioriza la marca que aparece PRIMERO
    en el texto (típicamente el emisor real; el resto son clones / inspirados en).

    Empate de posición → marca más larga gana (ej. "Dolce & Gabbana" sobre "Dolce").
    """
    t = _strip_accents(title).lower()
    # Quitar prefijo "Perfume" / "PERFUME" para no afectar la búsqueda por posición
    t = re.sub(r"^\s*perfume\s+", "", t, flags=re.IGNORECASE)
    # Normalizar " AND " → " & " para que matchee con brands tipo "dolce & gabbana"
    t = re.sub(r"\s+and\s+", " & ", t, flags=re.IGNORECASE)

    matches: list[tuple[int, int, str]] = []  # (posición, -longitud, brand_key)
    for brand in KNOWN_BRANDS:
        m = re.search(rf"\b{re.escape(brand)}\b", t)
        if m:
            matches.append((m.start(), -len(brand), brand))
    if not matches:
        return None
    matches.sort()
    return matches[0][2].title().replace("&", "&")


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
    if NON_PERFUME_BLOCK.search(title):
        return None

    # Extraer volumen y concentración del título ORIGINAL — el pre-clean (que mata
    # "clon X..." y similares) puede eliminar el "100 ML" final.
    volume = _extract_volume(title)
    if volume is None:
        return None
    concentration = _extract_concentration(title)
    gender = _extract_gender(title)

    # Pre-clean SOLO para detección de marca: elimina referencias a marcas
    # competidoras ("inspirado en X", "(clone of Y)") para que el _extract_brand
    # no las confunda con la marca real.
    pre_cleaned = title
    for pattern in PRE_BRAND_NOISE:
        pre_cleaned = re.sub(pattern, "", pre_cleaned, flags=re.IGNORECASE)

    raw_brand = _extract_brand(pre_cleaned) or fallback_brand
    if not raw_brand:
        return None

    # Pasa la marca por el canonicalizador: une casing/aliases/typos.
    brand = canonicalize_brand(raw_brand)
    if not brand:
        return None

    name = _clean_name(pre_cleaned, raw_brand, concentration, volume)
    # Si tras limpiar el nombre queda vacío, es porque el producto es "el base"
    # de la marca (e.g. "Dolce & Gabbana Pour Femme Edp 100ML" → name vacío).
    # Usamos el género detectado como nombre, o un fallback genérico.
    if not name:
        if gender == "Hombre":
            name = "Pour Homme"
        elif gender == "Mujer":
            name = "Pour Femme"
        else:
            name = "Original"

    slug = _slugify(f"{brand} {name} {concentration or ''} {volume}")
    return NormalizedProduct(
        brand=brand.strip(),
        name=name.strip(),
        concentration=concentration,
        volume_ml=volume,
        gender=gender,
        canonical_slug=slug,
    )
