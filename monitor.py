import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.2dehands.be"

# =========================
# CONFIG
# =========================

MIN_PRICE = 1300
MAX_PRICE = 1800

TARGET_MIN_PRICE = 1500
TARGET_MAX_PRICE = 1700

RIDER_HEIGHT_CM = 178
RIDER_INSEAM_CM = 86

ONLY_NEW = os.getenv("ONLY_NEW", "true").lower() == "true"
TEST_MODE = os.getenv("TEST_MODE", "false").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

SEEN_FILE = Path("seen.json")

SEARCH_URLS = [
    "https://www.2dehands.be/l/fietsen-en-brommers/fietsen-racefietsen/q/tijdritfiets/",
    "https://www.2dehands.be/l/fietsen-en-brommers/fietsen-racefietsen/q/tijdrit%2Bfiets/",
    "https://www.2dehands.be/l/fietsen-en-brommers/fietsen-racefietsen/q/tijdrit/",
]

TARGET_PROVINCES = [
    "west-vlaanderen",
    "oost-vlaanderen",
]

TT_KEYWORDS = [
    "tijdrit",
    "tijdritfiets",
    "triatlon",
    "triathlon",
    "tt bike",
    "tt-bike",
    "chrono",
    "timemachine",
    "speed concept",
    "shiv",
    "dean",
    "plasma",
    "p3",
    "p5",
]

POWER_KEYWORDS = [
    "powermeter",
    "power meter",
    "power meter",
    "vermogensmeter",
    "wattagemeter",
    "wattage meter",
    "4iiii",
    "4iiii",
    "stages",
    "quarq",
    "rotor 2inpower",
    "rotor inpower",
    "favero assioma",
    "garmin rally",
    "garmin vector",
    "sram axs power",
    "sram red axs power",
    "shimano power meter",
    "ultegra r8100-p",
    "dura ace r9200-p",
]

SIZE_KEYWORDS = [
    "maat m",
    "maat medium",
    "maat 54",
    "maat 55",
    "maat 56",
    "size m",
    "size medium",
    "54 cm",
    "55 cm",
    "56 cm",
]


# =========================
# HELPERS
# =========================

def normalize(text):
    return re.sub(r"\s+", " ", text.lower()).strip()


def load_seen():
    if not SEEN_FILE.exists():
        return set()

    try:
        return set(json.loads(SEEN_FILE.read_text()))
    except Exception:
        return set()


def save_seen(seen):
    SEEN_FILE.write_text(
        json.dumps(sorted(seen), indent=2, ensure_ascii=False)
    )


def get_price(text):
    """
    Detect common Belgian price formats:
    € 1.500
    €1.500,00
    1500 euro
    """

    patterns = [
        r"€\s*([\d\.\,]+)",
        r"([\d\.\,]+)\s*euro",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if not match:
            continue

        value = match.group(1)

        # Belgian format: 1.500,00
        if "." in value and "," in value:
            value = value.replace(".", "").replace(",", ".")
        elif "," in value:
            value = value.replace(",", ".")
        elif value.count(".") == 1:
            left, right = value.split(".")

            if len(right) == 3:
                value = value.replace(".", "")

        try:
            return float(value)
        except ValueError:
            pass

    return None


def contains_any(text, keywords):
    return any(keyword in text for keyword in keywords)


def extract_listing_links(html):
    soup = BeautifulSoup(html, "html.parser")

    results = []

    for link in soup.find_all("a", href=True):
        href = link["href"]

        if "/v/" not in href:
            continue

        absolute = urljoin(BASE_URL, href)

        title = link.get_text(" ", strip=True)

        if not title:
            title = link.get("aria-label", "")

        results.append({
            "url": absolute,
            "title": title,
        })

    # Deduplicate
    unique = {}

    for item in results:
        unique[item["url"]] = item

    return list(unique.values())


def fetch(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; "
            "TTBikeMonitor/1.0; +https://github.com/)"
        ),
        "Accept-Language": "nl-BE,nl;q=0.9,en;q=0.8",
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    return response.text


def get_listing_details(url):
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    text = normalize(soup.get_text(" ", strip=True))

    title = ""

    if soup.title:
        title = soup.title.get_text(" ", strip=True)

    return {
        "url": url,
        "title": title,
        "text": text,
    }


# =========================
# FILTER
# =========================

def evaluate_listing(listing):
    text = listing["text"]

    price = get_price(text)

    if price is None:
        return None

    if price < MIN_PRICE or price > MAX_PRICE:
        return None

    # TT / triathlon requirement
    if not contains_any(text, TT_KEYWORDS):
        return None

    # Province requirement
    if not contains_any(text, TARGET_PROVINCES):
        return None

    # Power meter is HARD requirement
    has_power_meter = contains_any(text, POWER_KEYWORDS)

    if not has_power_meter:
        return None

    has_target_size = contains_any(text, SIZE_KEYWORDS)

    if TARGET_MIN_PRICE <= price <= TARGET_MAX_PRICE:
        deal_class = "BUDGET"
    elif price < TARGET_MIN_PRICE:
        deal_class = "UNDER_BUDGET"
    else:
        deal_class = "OVER_TARGET"

    return {
        "url": listing["url"],
        "title": listing["title"],
        "price": price,
        "has_power_meter": has_power_meter,
        "has_target_size": has_target_size,
        "deal_class": deal_class,
    }


# =========================
# TELEGRAM
# =========================

def send_telegram(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Telegram secrets ontbreken.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    response = requests.post(
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


def format_message(item):
    size = (
        "📏 Maat lijkt interessant"
        if item["has_target_size"]
        else "📏 Maat controleren"
    )

    return (
        f"🚨 NIEUWE TT-DEAL\n\n"
        f"{item['title']}\n"
        f"💶 €{item['price']:,.0f}\n"
        f"⚡ Powermeter gevonden\n"
        f"{size}\n"
        f"📍 West-/Oost-Vlaanderen\n\n"
        f"🔗 {item['url']}"
    )


# =========================
# MAIN
# =========================

def main():
    print("=== 2dehands TT Bike Monitor ===")
    print(f"ONLY_NEW={ONLY_NEW}")
    print(f"TEST_MODE={TEST_MODE}")
    print(f"DRY_RUN={DRY_RUN}")

    seen = load_seen()

    print(f"Reeds geziene advertenties: {len(seen)}")

    all_candidates = {}

    for search_url in SEARCH_URLS:
        print(f"Zoeken: {search_url}")

        try:
            html = fetch(search_url)
            links = extract_listing_links(html)

            print(f"  {len(links)} links gevonden")

            for item in links:
                all_candidates[item["url"]] = item

            time.sleep(2)

        except Exception as exc:
            print(f"FOUT bij zoekpagina: {exc}")

    print(f"Totaal unieke links: {len(all_candidates)}")

    matches = []

    for index, candidate in enumerate(all_candidates.values(), start=1):
        url = candidate["url"]

        # New-only filter
        if ONLY_NEW and url in seen and not TEST_MODE:
            continue

        try:
            details = get_listing_details(url)
            result = evaluate_listing(details)

            if result:
                matches.append(result)
                print(
                    f"MATCH: €{result['price']:.0f} "
                    f"{result['title'][:100]}"
                )

            # Small delay between listing requests
            time.sleep(1)

        except Exception as exc:
            print(f"FOUT bij {url}: {exc}")

        # Prevent runaway scraping
        if index >= 50:
            print("Maximaal 50 advertenties gecontroleerd.")
            break

    # TEST_MODE:
    # existing ads are allowed to appear.
    if TEST_MODE:
        print("\nTEST MODE: bestaande matches mogen worden gemeld.")

    if not matches:
        print("Geen matches.")
    else:
        print(f"\n{len(matches)} match(es) gevonden.")

    for item in matches:
        message = format_message(item)

        print("\n---")
        print(message)

        if not DRY_RUN:
            send_telegram(message)

    # Mark everything we inspected as seen.
    # This is what makes ONLY_NEW work on future runs.
    for url in all_candidates:
        seen.add(url)

    save_seen(seen)

    print(f"\nSeen database: {len(seen)} advertenties.")

    return 0


if __name__ == "__main__":
    sys.exit(main())