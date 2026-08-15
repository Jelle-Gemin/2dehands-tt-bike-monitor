import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "https://www.2dehands.be"

# Hard maximum budget.
MAX_BUDGET = int(os.getenv("MAX_BUDGET", "1700"))

# Rider profile
RIDER_HEIGHT_CM = 178
RIDER_INSEAM_CM = 86

# Behaviour flags
ONLY_NEW = os.getenv("ONLY_NEW", "true").lower() == "true"
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

# Maximum number of individual listings inspected per run.
MAX_LISTINGS_PER_RUN = int(
    os.getenv("MAX_LISTINGS_PER_RUN", "75")
)

# Delay between requests.
REQUEST_DELAY_SECONDS = float(
    os.getenv("REQUEST_DELAY_SECONDS", "1.5")
)

SEEN_FILE = Path("seen.json")


# ============================================================
# 2DEHANDS SEARCHES
# ============================================================

SEARCH_URLS = [
    "https://www.2dehands.be/l/fietsen-en-brommers/fietsen-racefietsen/q/tijdritfiets/",
    "https://www.2dehands.be/l/fietsen-en-brommers/fietsen-racefietsen/q/tijdrit%2Bfiets/",
    "https://www.2dehands.be/l/fietsen-en-brommers/fietsen-racefietsen/q/tijdrit/",
    "https://www.2dehands.be/l/fietsen-en-brommers/fietsen-racefietsen/q/triatlon/",
    "https://www.2dehands.be/l/fietsen-en-brommers/fietsen-racefietsen/q/triathlon/",
    "https://www.2dehands.be/l/fietsen-en-brommers/fietsen-racefietsen/q/triatlon%2Bfiets/",
    "https://www.2dehands.be/l/fietsen-en-brommers/fietsen-racefietsen/q/triathlon%2Bfiets/",
    "https://www.2dehands.be/l/fietsen-en-brommers/fietsen-racefietsen/q/tt%2Bfiets/",
]


# ============================================================
# LOCATION FILTER
# ============================================================

WEST_FLANDERS_LOCATIONS = {
    "aalbeke",
    "alveringem",
    "ardooie",
    "avelgem",
    "beernem",
    "blankenberge",
    "bovekerke",
    "bredene",
    "brugge",
    "damme",
    "de haan",
    "de panne",
    "deerlijk",
    "diksmuide",
    "gistel",
    "harelbeke",
    "heist",
    "heuvelland",
    "houthulst",
    "ichtegem",
    "ingelmunster",
    "jabbeke",
    "knokke",
    "koekelare",
    "koksijde",
    "kortemark",
    "kortrijk",
    "langemark",
    "langemark-poelkapelle",
    "ledegem",
    "ieper",
    "leper",
    "lo-reninge",
    "menen",
    "meulebeke",
    "middelkerke",
    "nieuwpoort",
    "oostkamp",
    "oostende",
    "pittem",
    "poperinge",
    "roeselare",
    "ruiselede",
    "staden",
    "torhout",
    "veurne",
    "waregem",
    "wervik",
    "wevelgem",
    "wingene",
    "zedelgem",
    "zonnebeke",
    "zuienkerke",
    "zwevegem",
}

EAST_FLANDERS_LOCATIONS = {
    "aalst",
    "assenede",
    "brakel",
    "deinze",
    "destelbergen",
    "denderleeuw",
    "dendermonde",
    "de pinte",
    "evergem",
    "geraardsbergen",
    "gent",
    "grembergen",
    "hamme",
    "haaltert",
    "herzele",
    "kluisbergen",
    "kruisem",
    "lede",
    "lochristi",
    "lokeren",
    "maarkedal",
    "maldegem",
    "merelbeke",
    "nazareth",
    "nevele",
    "ninove",
    "oudenaarde",
    "ronse",
    "sint-amandsberg",
    "sint-laureins",
    "sint-niklaas",
    "stekene",
    "temse",
    "waarschoot",
    "wachtebeke",
    "wetteren",
    "wichelen",
    "zele",
    "zottegem",
    "zwalm",
}

TARGET_PROVINCES = {
    "west-vlaanderen",
    "west vlaanderen",
    "oost-vlaanderen",
    "oost vlaanderen",
}

TARGET_LOCATIONS = (
    WEST_FLANDERS_LOCATIONS
    | EAST_FLANDERS_LOCATIONS
)


# ============================================================
# TT / TRIATHLON KEYWORDS
# ============================================================

TT_KEYWORDS = {
    # Nederlands
    "tijdritfiets",
    "tijdrit fiets",
    "tijdrit-fiets",
    "tijdrit",
    "triatlonfiets",
    "triatlon fiets",
    "triatlon-fiets",
    "triatlon",
    "triathlonfiets",
    "triathlon fiets",
    "triathlon-fiets",
    "triathlon",

    # Engels / internationaal
    "time trial",
    "time-trial",
    "timetrial",
    "time trial bike",
    "time-trial bike",
    "tt bike",
    "tt-bike",
    "tt fiets",
    "tt-fiets",
    "tri bike",
    "tri-bike",

    # Algemene TT-termen
    "chrono",
    "tt frame",

    # Bekende TT-modellen
    "bmc timemachine",
    "trek speed concept",
    "cervelo p3",
    "cervélo p3",
    "cervelo p5",
    "cervélo p5",
    "specialized shiv",
    "canyon speedmax",
    "giant trinity",
    "scott plasma",
    "ridley dean",
    "felt ia",
    "felt da",
    "cannondale slice",
    "cube aerium",
    "merida warp",
    "merida time warp",
    "isaac muon",
}


# ============================================================
# POWER METER KEYWORDS
# ============================================================

POWER_KEYWORDS = {
    "powermeter",
    "power meter",
    "power-meter",
    "vermogensmeter",
    "vermogens meter",
    "wattagemeter",
    "wattage meter",
    "4iiii",
    "stages",
    "quarq",
    "rotor 2inpower",
    "rotor inpower",
    "rotor power",
    "favero assioma",
    "assioma",
    "garmin rally",
    "garmin vector",
    "sram axs power",
    "sram red axs power",
    "sram force axs power",
    "shimano power meter",
    "ultegra r8100-p",
    "dura ace r9200-p",
    "r8100-p",
    "r9200-p",
}


# ============================================================
# SIZE KEYWORDS
# ============================================================

SIZE_KEYWORDS = {
    "maat m",
    "maat medium",
    "size m",
    "size medium",
    "maat 54",
    "maat 55",
    "maat 56",
    "size 54",
    "size 55",
    "size 56",
    "54 cm",
    "55 cm",
    "56 cm",
}


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    ),
    "Accept-Language": "nl-BE,nl;q=0.9,en;q=0.8",
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
})


# ============================================================
# GENERAL HELPERS
# ============================================================

def normalize(text):
    if not text:
        return ""

    text = str(text).lower()
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def load_seen():
    if not SEEN_FILE.exists():
        return {}

    try:
        data = json.loads(
            SEEN_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(data, dict):
            return data

    except Exception as exc:
        print(
            f"WAARSCHUWING: seen.json kon niet "
            f"worden gelezen: {exc}"
        )

    return {}


def save_seen(seen):
    SEEN_FILE.write_text(
        json.dumps(
            seen,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def contains_any(text, keywords):
    text = normalize(text)

    return any(
        keyword in text
        for keyword in keywords
    )


# ============================================================
# PRICE PARSING
# ============================================================

def parse_price_value(value):
    """
    Parseert een numerieke prijs.

    Voorbeelden:

        1500
        1.500
        1.500,00
        1500,00
        1 500
    """

    if value is None:
        return None

    value = str(value).strip()

    value = value.replace("€", "")
    value = value.replace("EUR", "")
    value = value.replace("eur", "")
    value = value.replace("\xa0", " ")
    value = value.strip()

    # Spaties als duizendtalseparator.
    value = value.replace(" ", "")

    if not value:
        return None

    if "." in value and "," in value:
        # 1.500,00
        value = value.replace(".", "")
        value = value.replace(",", ".")

    elif "," in value:
        # 1500,00
        value = value.replace(",", ".")

    elif value.count(".") == 1:
        left, right = value.split(".")

        if len(right) == 3:
            # 1.500
            value = left + right

    try:
        return float(value)

    except (ValueError, TypeError):
        return None


def is_sane_price(price):
    """
    Sanity check voor een echte advertentieprijs.

    Dit voorkomt dat bijvoorbeeld een jaar, aantal views
    of een willekeurig ander getal als prijs wordt gebruikt.
    """

    if price is None:
        return False

    return 1 <= price <= 1000000


def parse_price_value_from_text(value):
    """
    Alleen gebruiken op een element waarvan we al weten dat
    het een PRIJS-ELEMENT is.

    BELANGRIJK:
    Deze functie wordt NOOIT uitgevoerd op de volledige
    advertentiebeschrijving.
    """

    if not value:
        return None

    value = normalize(value)

    match = re.search(
        r"(?:€\s*)?([\d\.,]+)\s*(?:euro|€)?",
        value,
        re.IGNORECASE,
    )

    if not match:
        return None

    price = parse_price_value(
        match.group(1)
    )

    if is_sane_price(price):
        return price

    return None


# ============================================================
# SAFE PRICE EXTRACTION
# ============================================================

def extract_price_from_json_ld(soup):
    """
    Probeert de prijs uit JSON-LD te halen.

    We accepteren uitsluitend velden die semantisch
    als offers/price zijn gemarkeerd.

    Dus NIET willekeurig zoeken naar bedragen in JSON.
    """

    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):

        raw = script.string

        if not raw:
            continue

        try:
            data = json.loads(raw)

        except Exception:
            continue

        objects = []

        if isinstance(data, dict):
            objects.append(data)

            graph = data.get("@graph")

            if isinstance(graph, list):
                objects.extend(
                    item
                    for item in graph
                    if isinstance(item, dict)
                )

        elif isinstance(data, list):
            objects.extend(
                item
                for item in data
                if isinstance(item, dict)
            )

        for item in objects:

            offers = item.get("offers")

            if isinstance(offers, dict):

                price = offers.get("price")

                if price is not None:
                    parsed = parse_price_value(
                        price
                    )

                    if is_sane_price(parsed):
                        return parsed, "jsonld_offers"

            elif isinstance(offers, list):

                for offer in offers:

                    if not isinstance(
                        offer,
                        dict,
                    ):
                        continue

                    price = offer.get("price")

                    if price is not None:
                        parsed = parse_price_value(
                            price
                        )

                        if is_sane_price(parsed):
                            return (
                                parsed,
                                "jsonld_offers",
                            )

    return None, None


def extract_price_from_meta(soup):
    """
    Probeert expliciet gemarkeerde prijs-meta-data te vinden.
    """

    selectors = [
        'meta[itemprop="price"]',
        'meta[property="product:price:amount"]',
        'meta[property="og:price:amount"]',
    ]

    for selector in selectors:

        element = soup.select_one(
            selector
        )

        if not element:
            continue

        content = element.get(
            "content"
        )

        price = parse_price_value(
            content
        )

        if is_sane_price(price):
            return price, selector

    return None, None


def extract_price_from_itemprop(soup):
    """
    Zoekt uitsluitend elementen die expliciet als price
    gemarkeerd zijn.

    Dit is veilig omdat we NIET de volledige pagina-tekst
    doorzoeken.
    """

    selectors = [
        '[itemprop="price"]',
        '[itemprop="lowPrice"]',
        '[itemprop="highPrice"]',
    ]

    for selector in selectors:

        for element in soup.select(
            selector
        ):

            content = (
                element.get("content")
                or element.get_text(
                    " ",
                    strip=True,
                )
            )

            price = parse_price_value(
                content
            )

            if is_sane_price(price):
                return price, selector

    return None, None


def extract_price_from_known_dom(soup):
    """
    Prijs uit bekende/waarschijnlijke 2dehands DOM-elementen.

    We gebruiken alleen elementen die specifiek bedoeld zijn
    voor prijsinformatie.

    NOOIT soup.get_text() gebruiken in deze functie.
    """

    selectors = [
        ".ListingHeader-module-price",

        # Mogelijke varianten.
        "[class*='ListingHeader-module-price']",
        "[class*='listingHeader'][class*='price']",
        "[class*='Listing'][class*='price']",

        # Algemene semantische price containers.
        "[data-testid='price']",
        "[data-test='price']",
        "[data-cy='price']",
        "[aria-label*='prijs' i]",
        "[aria-label*='price' i]",
    ]

    checked = set()

    for selector in selectors:

        try:
            elements = soup.select(
                selector
            )
        except Exception:
            continue

        for element in elements:

            # Niet meerdere keren exact hetzelfde element.
            element_id = id(element)

            if element_id in checked:
                continue

            checked.add(element_id)

            # Als een element expliciet aria-label "prijs"
            # heeft, is dat extra betrouwbaar.
            content = (
                element.get("content")
                or element.get_text(
                    " ",
                    strip=True,
                )
            )

            price = parse_price_value_from_text(
                content
            )

            if is_sane_price(price):
                return price, selector

    return None, None


def extract_price_from_scripts(soup):
    """
    Extra veiligheidslaag voor moderne client-side rendering.

    We zoeken NIET naar willekeurige bedragen.

    Alleen script-data waarin een expliciete prijs-key voorkomt
    wordt onderzocht.

    Deze functie is bewust conservatief.
    """

    price_keys = {
        "price",
        "pricevalue",
        "listingprice",
        "askingprice",
        "saleprice",
    }

    for script in soup.find_all("script"):

        raw = script.string

        if not raw:
            continue

        raw_normalized = normalize(raw)

        # Alleen scripts waarin expliciete price-gerelateerde
        # keys voorkomen.
        if not any(
            key in raw_normalized
            for key in price_keys
        ):
            continue

        # JSON proberen.
        try:
            data = json.loads(raw)
        except Exception:
            data = None

        def inspect_object(obj):
            if isinstance(obj, dict):

                for key, value in obj.items():

                    normalized_key = normalize(
                        key
                    ).replace(
                        "_",
                        ""
                    ).replace(
                        "-",
                        ""
                    )

                    if normalized_key in price_keys:

                        price = parse_price_value(
                            value
                        )

                        if is_sane_price(price):
                            return price

                    result = inspect_object(
                        value
                    )

                    if result is not None:
                        return result

            elif isinstance(obj, list):

                for item in obj:

                    result = inspect_object(
                        item
                    )

                    if result is not None:
                        return result

            return None

        if data is not None:

            price = inspect_object(
                data
            )

            if is_sane_price(price):
                return price, "script_json_price"

    return None, None


def extract_authoritative_price(soup):
    """
    Centrale prijsfunctie.

    Volgorde:

        1. JSON-LD offers.price
        2. meta itemprop/product price
        3. itemprop=price
        4. bekende 2dehands DOM
        5. expliciete JSON/script prijs

    BELANGRIJK:

    Er wordt nergens een bedrag uit de volledige
    advertentiebeschrijving gehaald.
    """

    methods = [
        extract_price_from_json_ld,
        extract_price_from_meta,
        extract_price_from_itemprop,
        extract_price_from_known_dom,
        extract_price_from_scripts,
    ]

    for method in methods:

        price, source = method(
            soup
        )

        if is_sane_price(price):
            return {
                "price": price,
                "source": source,
            }

    return {
        "price": None,
        "source": None,
    }


# ============================================================
# LOCATION
# ============================================================

def detect_location(location_text):

    location_text = normalize(
        location_text
    )

    if not location_text:
        return {
            "allowed": False,
            "province": None,
            "location": None,
            "location_raw": None,
        }

    if (
        "west-vlaanderen" in location_text
        or "west vlaanderen" in location_text
    ):
        return {
            "allowed": True,
            "province": "West-Vlaanderen",
            "location": location_text.title(),
            "location_raw": location_text,
        }

    if (
        "oost-vlaanderen" in location_text
        or "oost vlaanderen" in location_text
    ):
        return {
            "allowed": True,
            "province": "Oost-Vlaanderen",
            "location": location_text.title(),
            "location_raw": location_text,
        }

    for location in sorted(
        TARGET_LOCATIONS,
        key=len,
        reverse=True,
    ):

        pattern = (
            r"(?<![a-z])"
            + re.escape(location)
            + r"(?![a-z])"
        )

        if re.search(
            pattern,
            location_text,
        ):

            if location in WEST_FLANDERS_LOCATIONS:
                province = "West-Vlaanderen"
            else:
                province = "Oost-Vlaanderen"

            return {
                "allowed": True,
                "province": province,
                "location": location_text.title(),
                "location_raw": location_text,
            }

    return {
        "allowed": False,
        "province": None,
        "location": None,
        "location_raw": location_text,
    }


# ============================================================
# TT DETECTION
# ============================================================

def is_tt_or_triathlon(text):
    return contains_any(
        text,
        TT_KEYWORDS,
    )


# ============================================================
# POWER METER DETECTION
# ============================================================

def detect_power_meter(text):
    return contains_any(
        text,
        POWER_KEYWORDS,
    )


# ============================================================
# SIZE DETECTION
# ============================================================

def has_probable_size(text):
    return contains_any(
        text,
        SIZE_KEYWORDS,
    )


# ============================================================
# SEARCH PAGE PRICE EXTRACTION
# ============================================================

def extract_explicit_price_from_element(element):
    """
    Probeert een prijs te halen uit een element dat zelf
    duidelijk een prijs-element is.

    Dit is NIET hetzelfde als de volledige tekst van een
    advertentiekaart scannen.
    """

    selectors = [
        '[itemprop="price"]',
        '[data-testid="price"]',
        '[data-test="price"]',
        '[data-cy="price"]',
        '[class*="price"]',
        '[class*="Price"]',
    ]

    for selector in selectors:

        try:
            children = element.select(
                selector
            )
        except Exception:
            children = []

        for child in children:

            content = (
                child.get("content")
                or child.get_text(
                    " ",
                    strip=True,
                )
            )

            price = parse_price_value_from_text(
                content
            )

            if is_sane_price(price):
                return price

    return None


def extract_search_card_price(link):
    """
    Probeert de prijs uit de zoekresultaatkaart te halen.

    We gaan vanaf de link omhoog naar beperkte containers.

    BELANGRIJK:

    We scannen nooit simpelweg de volledige kaarttekst met
    een regex. Alleen expliciete price-elementen zijn geldig.

    Hierdoor wordt bijvoorbeeld:

        "Nieuwprijs €11.500"

    niet als verkoopprijs geïnterpreteerd.
    """

    current = link

    # Maximaal enkele ouders omhoog.
    for _ in range(8):

        if current is None:
            break

        price = extract_explicit_price_from_element(
            current
        )

        if is_sane_price(price):
            return price, "search_card_price"

        current = current.parent

    return None, None


# ============================================================
# SEARCH PAGE PARSER
# ============================================================

def extract_listing_links(html):

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    results = {}

    for link in soup.find_all(
        "a",
        href=True,
    ):

        href = link["href"]

        if "/v/" not in href:
            continue

        url = urljoin(
            BASE_URL,
            href,
        )

        # Remove query parameters.
        url = url.split("?")[0]

        title = link.get_text(
            " ",
            strip=True,
        )

        if not title:
            title = link.get(
                "aria-label",
                "",
            )

        # Probeer alleen de expliciet weergegeven
        # zoekresultaatprijs te vinden.
        search_price, price_source = (
            extract_search_card_price(
                link
            )
        )

        if url not in results:

            results[url] = {
                "url": url,
                "title": title,
                "search_price": search_price,
                "search_price_source": price_source,
            }

        else:

            # Als dezelfde advertentie via een andere zoekopdracht
            # opnieuw voorkomt en daar wel een prijs wordt gevonden,
            # bewaren we die.
            if (
                results[url].get(
                    "search_price"
                ) is None
                and search_price is not None
            ):
                results[url][
                    "search_price"
                ] = search_price

                results[url][
                    "search_price_source"
                ] = price_source

    return list(
        results.values()
    )


# ============================================================
# FETCH
# ============================================================

def fetch(url):

    response = SESSION.get(
        url,
        timeout=30,
    )

    response.raise_for_status()

    return response.text


# ============================================================
# LISTING DETAILS
# ============================================================

def get_listing_details(
    url,
    search_price=None,
    search_price_source=None,
):

    html = fetch(
        url
    )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    full_text = normalize(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = ""

    og_title = soup.find(
        "meta",
        attrs={
            "property": "og:title"
        },
    )

    if (
        og_title
        and og_title.get("content")
    ):

        title = normalize(
            og_title.get(
                "content"
            )
        )

    if (
        not title
        and soup.title
    ):

        title = normalize(
            soup.title.get_text(
                " ",
                strip=True,
            )
        )

    # --------------------------------------------------------
    # AUTHORITATIVE PRICE
    # --------------------------------------------------------

    price_data = extract_authoritative_price(
        soup
    )

    price = price_data.get(
        "price"
    )

    price_source = price_data.get(
        "source"
    )

    # --------------------------------------------------------
    # SEARCH PAGE PRICE FALLBACK
    # --------------------------------------------------------
    #
    # Alleen toegestaan wanneer de prijs expliciet uit een
    # prijs-element op de zoekresultaatkaart afkomstig was.
    #
    # NOOIT een bedrag uit full_text gebruiken.

    if price is None:

        if is_sane_price(
            search_price
        ):

            price = search_price

            price_source = (
                search_price_source
                or "search_card_price"
            )

    # --------------------------------------------------------
    # OFFICIËLE LOCATIE
    # --------------------------------------------------------

    location_element = soup.select_one(
        ".SellerLocationSection-module-locationName"
    )

    location_raw = ""

    if location_element:

        location_raw = normalize(
            location_element.get_text(
                " ",
                strip=True,
            )
        )

    # Mogelijke fallback voor gewijzigde DOM.
    if not location_raw:

        location_selectors = [
            "[class*='SellerLocationSection']",
            "[class*='locationName']",
            "[itemprop='addressLocality']",
        ]

        for selector in location_selectors:

            element = soup.select_one(
                selector
            )

            if not element:
                continue

            location_raw = normalize(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            if location_raw:
                break

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    json_ld_data = []

    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):

        try:

            raw = script.string

            if not raw:
                continue

            parsed = json.loads(
                raw
            )

            json_ld_data.append(
                parsed
            )

        except Exception:
            continue

    return {
        "url": url,
        "title": title,

        # Alleen betrouwbare prijsbronnen.
        "price": price,
        "price_source": price_source,

        "location_raw": location_raw,

        # Alleen voor inhoudelijke detectie.
        "text": full_text,

        "json_ld": json_ld_data,
    }


# ============================================================
# EVALUATION
# ============================================================

def evaluate_listing(listing):

    text = listing["text"]

    # --------------------------------------------------------
    # PRICE
    # --------------------------------------------------------

    price = listing.get(
        "price"
    )

    if price is None:

        return {
            "match": False,
            "reason": "geen_prijs",
            "price_source": listing.get(
                "price_source"
            ),
        }

    if price > MAX_BUDGET:

        return {
            "match": False,
            "reason": "boven_budget",
            "price": price,
            "price_source": listing.get(
                "price_source"
            ),
        }

    # --------------------------------------------------------
    # LOCATION
    # --------------------------------------------------------

    location = detect_location(
        listing.get(
            "location_raw",
            ""
        )
    )

    if not location["allowed"]:

        return {
            "match": False,
            "reason": "buiten_regio",
            "price": price,
            "price_source": listing.get(
                "price_source"
            ),
            "location": location.get(
                "location"
            ),
            "location_raw": location.get(
                "location_raw"
            ),
        }

    # --------------------------------------------------------
    # TT / TRIATHLON
    # --------------------------------------------------------

    if not is_tt_or_triathlon(
        text
    ):

        return {
            "match": False,
            "reason": "geen_tt_triathlon",
            "price": price,
            "price_source": listing.get(
                "price_source"
            ),
            "province": location[
                "province"
            ],
        }

    # --------------------------------------------------------
    # POWER METER
    # --------------------------------------------------------

    power_meter = detect_power_meter(
        text
    )

    # --------------------------------------------------------
    # SIZE
    # --------------------------------------------------------

    probable_size = has_probable_size(
        text
    )

    # --------------------------------------------------------
    # MATCH
    # --------------------------------------------------------

    return {
        "match": True,
        "reason": "match",

        "url": listing["url"],
        "title": listing["title"],

        "price": price,
        "price_source": listing.get(
            "price_source"
        ),

        "province": location[
            "province"
        ],
        "location": location[
            "location"
        ],

        "has_power_meter": power_meter,
        "probable_size": probable_size,

        "rider_height": RIDER_HEIGHT_CM,
        "rider_inseam": RIDER_INSEAM_CM,
    }


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    token = os.getenv(
        "TELEGRAM_BOT_TOKEN"
    )

    chat_id = os.getenv(
        "TELEGRAM_CHAT_ID"
    )

    if not token:

        print(
            "Telegram niet geconfigureerd: "
            "TELEGRAM_BOT_TOKEN ontbreekt."
        )

        return False

    if not chat_id:

        print(
            "Telegram niet geconfigureerd: "
            "TELEGRAM_CHAT_ID ontbreekt."
        )

        return False

    url = (
        "https://api.telegram.org/"
        f"bot{token}/sendMessage"
    )

    response = SESSION.post(
        url,
        json={
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=30,
    )

    response.raise_for_status()

    return True


def format_message(
    result,
    changed=False,
):

    if changed:
        header = (
            "🔄 PRIJS/ADVERTENTIE GEWIJZIGD"
        )
    else:
        header = "🚨 NIEUWE TT-DEAL"

    if result["has_power_meter"]:
        power_text = (
            "⚡ Powermeter: JA"
        )
    else:
        power_text = (
            "⚡ Powermeter: niet gevonden"
        )

    if result["probable_size"]:

        size_text = (
            "📏 Maat: mogelijk interessant "
            "(54–56/M gevonden)"
        )

    else:

        size_text = (
            "📏 Maat: niet duidelijk vermeld"
        )

    price_source = result.get(
        "price_source"
    )

    if price_source:
        price_source_text = (
            f"🔎 Prijsbron: {price_source}"
        )
    else:
        price_source_text = ""

    return (
        f"{header}\n\n"
        f"{result['title']}\n\n"
        f"💶 €{result['price']:,.0f}\n"
        f"📍 {result['location']} "
        f"({result['province']})\n"
        f"{power_text}\n"
        f"{size_text}\n"
        f"{price_source_text}\n"
        f"👤 Profiel: "
        f"{RIDER_HEIGHT_CM} cm / "
        f"{RIDER_INSEAM_CM} cm\n\n"
        f"🔗 {result['url']}"
    )


def send_no_matches_message(
    stats
):

    message = (
        "ℹ️ 2dehands TT-monitor\n\n"
        "Geen nieuwe matches gevonden.\n\n"
        f"💰 Max. budget: €{MAX_BUDGET}\n"
        "📍 West- en Oost-Vlaanderen\n"
        "🚴 TT / tijdrit / triathlon\n"
        "⚡ Powermeter: niet verplicht\n"
        f"👤 Profiel: "
        f"{RIDER_HEIGHT_CM} cm / "
        f"{RIDER_INSEAM_CM} cm\n\n"
        f"🔎 Gecontroleerd: "
        f"{stats['inspected']} advertenties"
    )

    if DRY_RUN:

        print()
        print("-" * 60)
        print(message)
        print("-" * 60)
        print(
            "DRY_RUN=true → "
            "Telegram NIET verstuurd."
        )

        return

    try:

        send_telegram(
            message
        )

        print(
            "Telegram: "
            "geen-match melding verstuurd."
        )

    except Exception as exc:

        print(
            f"Telegram fout bij "
            f"geen-match melding: {exc}"
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print(
        "2DEHANDS TT / TRIATHLON MONITOR"
    )
    print("=" * 60)

    print(
        f"MAX_BUDGET       = €{MAX_BUDGET}"
    )

    print(
        f"ONLY_NEW         = {ONLY_NEW}"
    )

    print(
        f"TEST_MODE        = {TEST_MODE}"
    )

    print(
        f"DRY_RUN          = {DRY_RUN}"
    )

    print(
        f"MAX_LISTINGS     = "
        f"{MAX_LISTINGS_PER_RUN}"
    )

    print(
        f"RIDER            = "
        f"{RIDER_HEIGHT_CM} cm / "
        f"{RIDER_INSEAM_CM} cm"
    )

    print(
        "POWER METER      = "
        "OPTIONEEL"
    )

    print(
        "PRICE SOURCE     = "
        "ALLEEN AUTHORITATIVE DOM / JSON / SEARCH PRICE"
    )

    seen = load_seen()

    print(
        f"Reeds opgeslagen advertenties: "
        f"{len(seen)}"
    )

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    all_candidates = {}

    for search_url in SEARCH_URLS:

        print()
        print(
            f"Zoeken: {search_url}"
        )

        try:

            html = fetch(
                search_url
            )

            links = extract_listing_links(
                html
            )

            print(
                f"  {len(links)} links gevonden"
            )

            for item in links:

                url = item["url"]

                if url not in all_candidates:

                    all_candidates[
                        url
                    ] = item

                else:

                    # Neem prijs over wanneer een andere
                    # zoekopdracht hem wel vond.
                    if (
                        all_candidates[url].get(
                            "search_price"
                        ) is None
                        and item.get(
                            "search_price"
                        ) is not None
                    ):

                        all_candidates[url][
                            "search_price"
                        ] = item[
                            "search_price"
                        ]

                        all_candidates[url][
                            "search_price_source"
                        ] = item[
                            "search_price_source"
                        ]

            time.sleep(
                REQUEST_DELAY_SECONDS
            )

        except Exception as exc:

            print(
                f"  FOUT: {exc}"
            )

    print()
    print(
        f"Totaal unieke links: "
        f"{len(all_candidates)}"
    )

    # --------------------------------------------------------
    # PROCESS LISTINGS
    # --------------------------------------------------------

    matches = []

    inspected = 0

    stats = {
        "inspected": 0,
        "boven_budget": 0,
        "buiten_regio": 0,
        "geen_tt_triathlon": 0,
        "geen_prijs": 0,
        "matches": 0,
        "matches_met_powermeter": 0,
        "matches_zonder_powermeter": 0,
        "errors": 0,
        "skipped_seen": 0,
        "rechecked_missing_price": 0,
    }

    for candidate in all_candidates.values():

        if (
            inspected
            >= MAX_LISTINGS_PER_RUN
        ):

            print(
                "Maximum aantal advertenties "
                "bereikt."
            )

            break

        url = candidate["url"]

        previous = seen.get(
            url
        )

        # ----------------------------------------------------
        # ONLY_NEW
        # ----------------------------------------------------
        #
        # BELANGRIJKE WIJZIGING:
        #
        # Advertenties die eerder geen prijs hadden, worden
        # NIET permanent overgeslagen.
        #
        # Dit is nodig omdat de oude parser 65 advertenties
        # met last_price=null heeft opgeslagen.

        if (
            ONLY_NEW
            and previous is not None
            and not TEST_MODE
        ):

            previous_price = previous.get(
                "last_price"
            )

            if previous_price is not None:

                stats[
                    "skipped_seen"
                ] += 1

                continue

            else:

                stats[
                    "rechecked_missing_price"
                ] += 1

                print()
                print(
                    "  HERCONTROLE: "
                    "advertentie had eerder "
                    "geen betrouwbare prijs."
                )

        inspected += 1

        stats[
            "inspected"
        ] = inspected

        print()
        print(
            f"[{inspected}] {url}"
        )

        try:

            listing = get_listing_details(
                url,
                search_price=candidate.get(
                    "search_price"
                ),
                search_price_source=candidate.get(
                    "search_price_source"
                ),
            )

            result = evaluate_listing(
                listing
            )

            current_price = result.get(
                "price"
            )

            old_price = None

            if previous:

                old_price = previous.get(
                    "last_price"
                )

            price_changed = (
                old_price is not None
                and current_price is not None
                and old_price != current_price
            )

            # ------------------------------------------------
            # SAVE CURRENT STATE
            # ------------------------------------------------

            seen[url] = {
                "last_price": current_price,

                "last_price_source": listing.get(
                    "price_source"
                ),

                "last_title": listing.get(
                    "title",
                    "",
                ),

                "last_location": result.get(
                    "location"
                ),

                "last_location_raw": result.get(
                    "location_raw"
                ),

                "last_province": result.get(
                    "province"
                ),

                "last_match": result.get(
                    "match",
                    False,
                ),

                "last_reason": result.get(
                    "reason"
                ),

                "last_has_power_meter": result.get(
                    "has_power_meter",
                    False,
                ),
            }

            # ------------------------------------------------
            # NO MATCH
            # ------------------------------------------------

            if not result.get(
                "match",
                False,
            ):

                reason = result.get(
                    "reason",
                    "onbekend",
                )

                stats[reason] = (
                    stats.get(
                        reason,
                        0,
                    ) + 1
                )

                print(
                    f"  SKIP: {reason}"
                )

                if current_price is not None:

                    print(
                        f"  prijs: "
                        f"€{current_price:.0f}"
                    )

                    print(
                        f"  prijsbron: "
                        f"{listing.get('price_source')}"
                    )

                else:

                    print(
                        "  prijs: "
                        "GEEN BETROUWBARE PRIJS"
                    )

                continue

            # ------------------------------------------------
            # MATCH
            # ------------------------------------------------

            stats[
                "matches"
            ] += 1

            if result[
                "has_power_meter"
            ]:

                stats[
                    "matches_met_powermeter"
                ] += 1

            else:

                stats[
                    "matches_zonder_powermeter"
                ] += 1

            was_previous_match = bool(
                previous
                and previous.get(
                    "last_match",
                    False,
                )
            )

            # ------------------------------------------------
            # NOTIFY
            # ------------------------------------------------

            should_notify = (
                TEST_MODE
                or previous is None
                or not was_previous_match
                or price_changed
            )

            if should_notify:

                matches.append({
                    "result": result,
                    "changed": price_changed,
                })

                print(
                    "  >>> NIEUWE MATCH!"
                )

                print(
                    f"  prijs: "
                    f"€{current_price:.0f}"
                )

                print(
                    f"  prijsbron: "
                    f"{listing.get('price_source')}"
                )

            else:

                print(
                    "  MATCH, maar reeds "
                    "eerder gemeld."
                )

        except Exception as exc:

            stats[
                "errors"
            ] += 1

            print(
                f"  FOUT bij advertentie: "
                f"{exc}"
            )

        time.sleep(
            REQUEST_DELAY_SECONDS
        )

    # --------------------------------------------------------
    # SAVE STATE
    # --------------------------------------------------------

    save_seen(
        seen
    )

    # --------------------------------------------------------
    # RESULTS
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("RESULTAAT")
    print("=" * 60)

    for key, value in stats.items():

        print(
            f"{key:30} {value}"
        )

    print()
    print(
        f"Nieuwe Telegram-meldingen: "
        f"{len(matches)}"
    )

    # --------------------------------------------------------
    # SEND MATCHES
    # --------------------------------------------------------

    for item in matches:

        result = item["result"]

        changed = item["changed"]

        message = format_message(
            result,
            changed=changed,
        )

        print()
        print("-" * 60)
        print(message)
        print("-" * 60)

        if DRY_RUN:

            print(
                "DRY_RUN=true → "
                "Telegram NIET verstuurd."
            )

        else:

            try:

                send_telegram(
                    message
                )

                print(
                    "Telegram verstuurd."
                )

            except Exception as exc:

                print(
                    f"Telegram fout: {exc}"
                )

    # --------------------------------------------------------
    # NO NEW MATCHES
    # --------------------------------------------------------

    if not matches:

        send_no_matches_message(
            stats
        )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    print()

    print(
        f"Seen database bevat nu "
        f"{len(seen)} advertenties."
    )

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    sys.exit(
        main()
    )