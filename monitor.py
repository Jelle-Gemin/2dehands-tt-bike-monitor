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

# Maximum aankoopprijs.
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
]


# ============================================================
# HARD LOCATION FILTER
# ============================================================

# We accepteren uitsluitend West- en Oost-Vlaanderen.
#
# De provincienaam zelf wordt gecontroleerd wanneer die in de
# advertentie voorkomt.
#
# Daarnaast gebruiken we gemeenten/steden, omdat 2dehands vaak
# alleen de plaatsnaam toont.

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
    "gooik",  # harmless fallback; can remove if desired
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
    "leper",
    "ieper",
    "lo-reninge",
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
    "spiere-helkijn",
    "staden",
    "torhout",
    "veurne",
    "vingem",
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
    "aardenburg",
    "assene",
    "assenede",
    "brakel",
    "deinze",
    "destelbergen",
    "denderleeuw",
    "dendermonde",
    "de pinte",
    "evergem",
    "geraardsbergen",
    "gente",
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
    "tijdrit",
    "tijdritfiets",
    "tijdrit fiets",
    "triatlon",
    "triathlon",
    "tt bike",
    "tt-bike",
    "tt fiets",
    "chrono",
    "time trial",
    "timetrial",
    "timemachine",
    "speed concept",
    "shiv",
    "dean",
    "plasma",
    "p3",
    "p5",
    "slice",
    "speedmax",
    "trinity",
    "foil tt",
    "aeroad tt",
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
    "wattagemeter",
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
# HTTP
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
    """
    Normaliseert tekst zodat zoeken op keywords betrouwbaarder wordt.
    """
    if not text:
        return ""

    text = text.lower()

    # Non-breaking spaces etc.
    text = text.replace("\xa0", " ")

    # Meerdere whitespace characters naar één spatie.
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def load_seen():
    """
    seen.json bevat:

    {
        "URL": {
            "last_price": 1500,
            "last_title": "...",
            "last_location": "...",
            "matched": true
        }
    }
    """

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
    """
    Controleert of één van de keywords in de tekst voorkomt.
    """

    text = normalize(text)

    return any(
        keyword in text
        for keyword in keywords
    )


# ============================================================
# PRICE
# ============================================================

def parse_price_value(value):
    """
    Probeert Belgische prijsnotaties te interpreteren.

    Voorbeelden:
        1.500
        1.500,00
        1500
        1500,00
    """

    value = value.strip()
    value = value.replace("€", "")
    value = value.replace("EUR", "")
    value = value.strip()

    if "." in value and "," in value:
        # 1.500,00
        value = value.replace(".", "")
        value = value.replace(",", ".")

    elif "," in value:
        # 1500,00
        value = value.replace(",", ".")

    elif value.count(".") == 1:
        left, right = value.split(".")

        # 1.500 -> 1500
        if len(right) == 3:
            value = left + right

    try:
        return float(value)
    except ValueError:
        return None


def get_price(text):
    """
    Zoekt een prijs in de advertentietekst.

    We proberen eerst expliciete euro-notaties.
    """

    patterns = [
        r"€\s*([\d\.,]+)",
        r"([\d\.,]+)\s*euro",
        r"prijs\s*[:\-]?\s*€?\s*([\d\.,]+)",
    ]

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text,
            re.IGNORECASE,
        )

        for match in matches:

            price = parse_price_value(match)

            if price is None:
                continue

            # Sanity check.
            # We willen geen jaartallen of andere getallen.
            if 50 <= price <= 100000:
                return price

    return None


# ============================================================
# LOCATION
# ============================================================

def detect_location(text):
    """
    Geeft terug:

        {
            "allowed": True/False,
            "province": "...",
            "location": "..."
        }

    Provincienaam heeft voorrang.
    Daarna controleren we gemeenten/steden.
    """

    text = normalize(text)

    # 1. Expliciete provincie
    if (
        "west-vlaanderen" in text
        or "west vlaanderen" in text
    ):
        return {
            "allowed": True,
            "province": "West-Vlaanderen",
            "location": "West-Vlaanderen",
        }

    if (
        "oost-vlaanderen" in text
        or "oost vlaanderen" in text
    ):
        return {
            "allowed": True,
            "province": "Oost-Vlaanderen",
            "location": "Oost-Vlaanderen",
        }

    # 2. Plaatsnaam
    #
    # We zoeken bewust als woordgrens om bijvoorbeeld
    # "gent" niet te laten matchen met een ander woord.

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

        if re.search(pattern, text):
            if location in WEST_FLANDERS_LOCATIONS:
                province = "West-Vlaanderen"
            else:
                province = "Oost-Vlaanderen"

            return {
                "allowed": True,
                "province": province,
                "location": location.title(),
            }

    return {
        "allowed": False,
        "province": None,
        "location": None,
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
# POWER METER
# ============================================================

def has_power_meter(text):
    return contains_any(
        text,
        POWER_KEYWORDS,
    )


# ============================================================
# SIZE
# ============================================================

def has_probable_size(text):
    return contains_any(
        text,
        SIZE_KEYWORDS,
    )


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

        # Strip query parameters where possible.
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

        results[url] = {
            "url": url,
            "title": title,
        }

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

def get_listing_details(url):
    html = fetch(url)

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    text = normalize(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    title = ""

    if soup.title:
        title = normalize(
            soup.title.get_text(
                " ",
                strip=True,
            )
        )

    # Try to find JSON-LD product/listing data.
    json_ld_data = []

    for script in soup.find_all(
        "script",
        type="application/ld+json",
    ):

        try:
            raw = script.string

            if not raw:
                continue

            parsed = json.loads(raw)

            json_ld_data.append(parsed)

        except Exception:
            continue

    return {
        "url": url,
        "title": title,
        "text": text,
        "json_ld": json_ld_data,
    }


# ============================================================
# EVALUATION
# ============================================================

def evaluate_listing(listing):
    """
    HARD FILTER ORDER:

    1. Price
    2. Location
    3. TT / triathlon
    4. Powermeter

    Daarna pas aanvullende informatie.
    """

    text = listing["text"]

    # --------------------------------------------------------
    # PRICE
    # --------------------------------------------------------

    price = get_price(text)

    if price is None:
        return {
            "match": False,
            "reason": "geen_prijs",
        }

    if price > MAX_BUDGET:
        return {
            "match": False,
            "reason": "boven_budget",
            "price": price,
        }

    # --------------------------------------------------------
    # LOCATION
    # --------------------------------------------------------

    location = detect_location(text)

    if not location["allowed"]:
        return {
            "match": False,
            "reason": "buiten_regio",
            "price": price,
        }

    # --------------------------------------------------------
    # TT / TRIATHLON
    # --------------------------------------------------------

    if not is_tt_or_triathlon(text):

        return {
            "match": False,
            "reason": "geen_tt_triathlon",
            "price": price,
            "province": location["province"],
        }

    # --------------------------------------------------------
    # POWER METER
    # --------------------------------------------------------

    if not has_power_meter(text):

        return {
            "match": False,
            "reason": "geen_powermeter",
            "price": price,
            "province": location["province"],
        }

    # --------------------------------------------------------
    # SIZE
    # --------------------------------------------------------

    probable_size = has_probable_size(text)

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    return {
        "match": True,
        "reason": "match",

        "url": listing["url"],
        "title": listing["title"],

        "price": price,

        "province": location["province"],
        "location": location["location"],

        "has_power_meter": True,
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


def format_message(result, changed=False):
    if result["probable_size"]:
        size_text = (
            "📏 Maat lijkt mogelijk geschikt "
            "(54–56/M gevonden)"
        )
    else:
        size_text = (
            "📏 Maat niet duidelijk vermeld — "
            "controleren"
        )

    if changed:
        header = "🔄 PRIJS/ADVERTENTIE GEWIJZIGD"
    else:
        header = "🚨 NIEUWE TT-DEAL"

    return (
        f"{header}\n\n"
        f"{result['title']}\n\n"
        f"💶 €{result['price']:,.0f}\n"
        f"📍 {result['location']} "
        f"({result['province']})\n"
        f"⚡ Powermeter gevonden\n"
        f"{size_text}\n"
        f"👤 Profiel: "
        f"{RIDER_HEIGHT_CM} cm / "
        f"{RIDER_INSEAM_CM} cm\n\n"
        f"🔗 {result['url']}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("2DEHANDS TT / TRIATHLON MONITOR")
    print("=" * 60)

    print(f"MAX_BUDGET       = €{MAX_BUDGET}")
    print(f"ONLY_NEW         = {ONLY_NEW}")
    print(f"TEST_MODE        = {TEST_MODE}")
    print(f"DRY_RUN          = {DRY_RUN}")
    print(f"MAX_LISTINGS     = {MAX_LISTINGS_PER_RUN}")
    print(
        f"RIDER            = "
        f"{RIDER_HEIGHT_CM} cm / "
        f"{RIDER_INSEAM_CM} cm"
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
                all_candidates[
                    item["url"]
                ] = item

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
        "boven_budget": 0,
        "buiten_regio": 0,
        "geen_tt_triathlon": 0,
        "geen_powermeter": 0,
        "geen_prijs": 0,
        "matches": 0,
        "errors": 0,
        "skipped_seen": 0,
    }

    for candidate in all_candidates.values():

        if inspected >= MAX_LISTINGS_PER_RUN:

            print(
                "Maximum aantal advertenties "
                "bereikt."
            )

            break

        url = candidate["url"]

        previous = seen.get(url)

        # ----------------------------------------------------
        # In TEST_MODE testen we bestaande advertenties opnieuw.
        # ----------------------------------------------------

        if (
            ONLY_NEW
            and previous is not None
            and not TEST_MODE
        ):

            stats["skipped_seen"] += 1

            continue

        inspected += 1

        print()
        print(
            f"[{inspected}] "
            f"{url}"
        )

        try:

            listing = get_listing_details(
                url
            )

            result = evaluate_listing(
                listing
            )

            # ------------------------------------------------
            # SAVE STATE
            #
            # Belangrijk:
            # We bewaren WEL dat we de advertentie bekeken
            # hebben, maar een match blijft apart.
            #
            # Daardoor kan een advertentie later opnieuw
            # matchen wanneer de prijs verandert.
            # ------------------------------------------------

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

            seen[url] = {
                "last_price": current_price,
                "last_title": listing.get(
                    "title",
                    "",
                ),
                "last_location": result.get(
                    "location"
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

                continue

            # ------------------------------------------------
            # MATCH
            # ------------------------------------------------

            stats["matches"] += 1

            # We sturen:
            #
            # - nieuwe matches
            # - OF opnieuw relevante matches wanneer de
            #   advertentie gewijzigd is.
            #
            # TEST_MODE forceert opnieuw een melding.
            # ------------------------------------------------

            was_previous_match = bool(
                previous
                and previous.get(
                    "last_match",
                    False,
                )
            )

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
                    "  >>> MATCH!"
                )

            else:

                print(
                    "  MATCH, maar reeds "
                    "eerder gemeld."
                )

        except Exception as exc:

            stats["errors"] += 1

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
            f"{key:20} {value}"
        )

    print()
    print(
        f"Nieuwe meldingen: "
        f"{len(matches)}"
    )

    # --------------------------------------------------------
    # SEND TELEGRAM
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
    # FINAL
    # --------------------------------------------------------

    print()
    print(
        f"Seen database bevat nu "
        f"{len(seen)} advertenties."
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )