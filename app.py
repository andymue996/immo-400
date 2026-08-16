# -*- coding: utf-8 -*-
"""
Immo-Aggregator Kempten (Allgäu) + 20 km
==========================================

Sammelt Immobilien-Kaufangebote aus mehreren Quellen:
- ohne-makler.net, VR Bank, Sparkasse Allgäu, Sozialbau, Hold Immobilien,
  BRIMO, Herzstuben  -> statisches HTML (requests + BeautifulSoup)
- ImmoScout24, Immowelt, Kleinanzeigen -> JavaScript-Seiten (Playwright)

WICHTIG - bitte vor dem ersten produktiven Einsatz lesen:
1. Die CSS-Selektoren für ImmoScout24/Immowelt/Kleinanzeigen sind Best-Guess
   und wurden NICHT live gegen die aktuellen Seiten getestet. Websites ändern
   ihr HTML häufig. Wenn ein Scraper 0 Treffer liefert: F12 im Browser öffnen,
   ein Angebots-Element inspizieren, Selektor in SELECTORS unten anpassen.
2. Diese Portale untersagen in ihren AGB automatisiertes Auslesen. Das Risiko
   (IP-Sperre, Abmahnung) liegt bei dir. Nutze es nur für den privaten
   Gebrauch, baue Wartezeiten zwischen Requests ein (siehe SLEEP_BETWEEN_REQ)
   und übertreib es nicht mit der Lauf-Frequenz (z.B. 1x täglich reicht).
3. Playwright braucht einen Chromium-Browser lokal installiert:
   pip install playwright beautifulsoup4 requests pandas streamlit
   playwright install chromium

Installation & Start:
    pip install -r requirements.txt
    playwright install chromium
    streamlit run immo_aggregator.py
"""

import sqlite3
import time
import random
import datetime
import re
import traceback

import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# ----------------------------------------------------------------------
# KONFIGURATION
# ----------------------------------------------------------------------

DB_NAME = "kempten_immobilien.db"
SLEEP_BETWEEN_REQ = (2, 5)  # Sekunden, zufällig gewählt -> weniger auffällig / fair

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9",
}

# PLZ im ca. 20km Radius um Kempten (87435). Bitte prüfen/ergänzen -
# das ist eine Näherung, keine exakte Umkreisberechnung.
PLZ_WHITELIST = [
    "87435", "87437", "87439",  # Kempten selbst
    "87448",  # Waltenhofen
    "87452",  # Altusried
    "87466",  # Oy-Mittelberg
    "87477",  # Sulzberg
    "87480",  # Weitnau (Rand des Radius)
    "87487",  # Wiggensbach
    "87493",  # Lauben / Durach
    "87509",  # Immenstadt
    "87616",  # Marktoberdorf (Rand)
    "87634",  # Obergünzburg
    "87642",  # Halblech (evtl. schon zu weit, prüfen)
]
ORT_WHITELIST = [
    "kempten", "waltenhofen", "altusried", "oy-mittelberg", "sulzberg",
    "weitnau", "wiggensbach", "durach", "lauben", "immenstadt",
    "marktoberdorf", "obergünzburg", "buchenberg", "dietmannsried",
]


def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS immobilien (
            id TEXT PRIMARY KEY,
            title TEXT,
            price REAL,
            rooms REAL,
            area REAL,
            location TEXT,
            url TEXT,
            source TEXT,
            status TEXT DEFAULT 'Neu',
            first_seen DATE
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS scrape_log (
            source TEXT PRIMARY KEY,
            last_run TEXT,
            found_count INTEGER,
            error TEXT
        )
    ''')
    conn.commit()
    conn.close()


def log_scrape(source, count, error=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO scrape_log (source, last_run, found_count, error)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(source) DO UPDATE SET last_run=excluded.last_run,
            found_count=excluded.found_count, error=excluded.error
    ''', (source, datetime.datetime.now().isoformat(timespec="seconds"), count, error))
    conn.commit()
    conn.close()


def extract_number(text, regex_pattern, default=None):
    match = re.search(regex_pattern, text, re.IGNORECASE)
    if match:
        try:
            val_str = match.group(1).replace(".", "").replace(",", ".")
            return float(val_str)
        except Exception:
            pass
    return default


def in_region(text):
    """Grobe Umkreis-Prüfung anhand PLZ oder Ortsname im Text."""
    t = text.lower()
    if any(plz in text for plz in PLZ_WHITELIST):
        return True
    if any(ort in t for ort in ORT_WHITELIST):
        return True
    return False


def polite_sleep():
    time.sleep(random.uniform(*SLEEP_BETWEEN_REQ))


# ----------------------------------------------------------------------
# STATISCHE SCRAPER (requests + BeautifulSoup)
# ----------------------------------------------------------------------

def _generic_static_scrape(source_name, url, card_selectors, price_default=None):
    """
    Versucht mehrere mögliche Karten-Selektoren nacheinander (Fallback-Kette),
    weil sich HTML-Klassen häufig ändern. Nur echte Treffer werden übernommen -
    Angebote OHNE erkennbaren Preis werden verworfen statt mit Phantasiewerten
    aufgefüllt.
    """
    items = []
    error = None
    try:
        res = requests.get(url, headers=HEADERS, timeout=12)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        cards = []
        for sel in card_selectors:
            found = soup.select(sel)
            if found:
                cards = found
                break

        for card in cards:
            text = card.get_text(" ", strip=True)
            if "€" not in text:
                continue
            if not in_region(text):
                continue

            title_elem = card.find(["h2", "h3", "h4", "a"])
            title = title_elem.get_text(strip=True) if title_elem else source_name

            link_elem = card.find("a", href=True)
            if not link_elem:
                continue
            link = link_elem["href"]
            if not link.startswith("http"):
                base = "/".join(url.split("/")[:3])
                link = base + (link if link.startswith("/") else "/" + link)

            price = extract_number(text, r'([\d\.]{4,})\s*€', default=price_default)
            rooms = extract_number(text, r'([\d,]+)\s*Zi', default=None)
            area = extract_number(text, r'([\d,\.]+)\s*m²', default=None)

            if price is None:
                continue  # kein verwertbarer Preis -> lieber weglassen als raten

            items.append({
                "id": f"{source_name.lower().replace(' ', '_')}_{abs(hash(link))}",
                "title": title[:100],
                "price": price,
                "rooms": rooms,
                "area": area,
                "location": "Kempten & Umland",
                "url": link,
                "source": source_name,
            })
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    log_scrape(source_name, len(items), error)
    polite_sleep()
    return items


def scrape_ohne_makler():
    """
    VERIFIZIERT (16.08.2026): Angebote sind serverseitig im HTML enthalten.
    Jede Karte ist EIN <a href="/immobilie/<ID>/">-Link, der Titel, Preis,
    PLZ/Ort und Eckdaten im Linktext bündelt. Deshalb hier kein Karten-Selektor
    (article/div-Klasse), sondern direkt der URL-Pattern-Ansatz - robuster,
    weil er nicht von wechselnden CSS-Klassen abhängt.
    """
    source_name = "ohne-makler.net"
    url = "https://www.ohne-makler.net/immobilien/wohnung-kaufen/bayern/kempten-allgau/"
    items = []
    error = None
    try:
        res = requests.get(url, headers=HEADERS, timeout=12)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        seen_ids = set()
        for a in soup.select('a[href*="/immobilie/"]'):
            href = a.get("href", "")
            m = re.search(r'/immobilie/(\d+)/', href)
            if not m:
                continue
            listing_id = m.group(1)
            if listing_id in seen_ids:
                continue  # jede Karte erscheint als Bild-Link UND Text-Link -> dedupen
            text = a.get_text(" ", strip=True)
            if "€" not in text or not in_region(text):
                continue

            link = href if href.startswith("http") else "https://www.ohne-makler.net" + href
            price = extract_number(text, r'([\d\.]{4,})\s*€', default=None)
            # Muster im Linktext: "... (Ort) <Zimmer> <Fläche>m²" -> Zahl direkt vor "m²" ist Fläche,
            # die Zahl davor ist die Zimmerzahl
            area = extract_number(text, r'([\d,\.]+)\s*m²', default=None)
            rooms = extract_number(text, r'(\d+)\s+[\d,\.]+\s*m²', default=None)
            if price is None:
                continue

            title = text.split("€")[0].strip()[:100]
            seen_ids.add(listing_id)
            items.append({
                "id": f"ohne_makler_{listing_id}",
                "title": title,
                "price": price,
                "rooms": rooms,
                "area": area,
                "location": "Kempten & Umland",
                "url": link,
                "source": source_name,
            })
    except Exception as e:
        error = f"{type(e).__name__}: {e}"

    log_scrape(source_name, len(items), error)
    polite_sleep()
    return items


def scrape_vr_bank():
    """
    GEPRÜFT (16.08.2026): Die Immobiliensuche läuft über ein eingebettetes
    FlowFact-Widget (https://432638.flowfact-sites.net/immoframe/), dessen
    robots.txt automatisierten Zugriff EXPLIZIT untersagt. Wir respektieren
    das und scrapen hier bewusst nichts - stattdessen nur ein Hinweis-Eintrag
    mit Link. Empfehlung: auf der VR-Bank-Seite einen kostenlosen
    E-Mail-Suchauftrag einrichten, das ist der offizielle Weg an diese Daten.
    """
    source_name = "VR Bank Kempten-Oberallgäu"
    log_scrape(source_name, 0, "Übersprungen: robots.txt des Anbieters verbietet Scraping (FlowFact-Widget). "
                                "Bitte manuell E-Mail-Suchauftrag einrichten.")
    return [{
        "id": "vr_bank_hinweis",
        "title": "VR Bank Immobiliensuche (manuell prüfen / E-Mail-Suchauftrag einrichten)",
        "price": None,
        "rooms": None,
        "area": None,
        "location": "Kempten & Umland",
        "url": "https://www.vrbank-ke-oa.de/privatkunden/immobilie-und-wohnen/produkte/immobilien/immobiliensuche.html",
        "source": source_name,
    }]


def scrape_sparkasse_allgaeu():
    """
    GEPRÜFT (16.08.2026): Next.js-Seite, Angebote werden erst per Client-side
    JavaScript nachgeladen (Platzhaltertext "Lädt..." im Server-HTML).
    requests+BeautifulSoup sieht daher NIE echte Angebote. Braucht Playwright
    (siehe PLAYWRIGHT_SCRAPERS) oder die zugrunde liegende API - letztere
    wurde hier nicht identifiziert.
    """
    source_name = "Sparkasse Allgäu"
    return _generic_playwright_scrape(
        source_name,
        "https://immobilien.sparkasse.de/immobilien/bayern/kempten.html",
        card_selector="a[href*='/immobilien/objekt']",  # Best-Guess, ggf. anpassen
        wait_selector=None,
    )


def scrape_sozialbau():
    return _generic_static_scrape(
        "Sozialbau Kempten",
        "https://www.sozialbau.de/leistungen/kaufen/",
        card_selectors=[".objekt", ".immo-teaser", "article", ".card"],
    )


def scrape_hold_immobilien():
    return _generic_static_scrape(
        "Hold Immobilien",
        "https://hold-immobilien.de/",
        card_selectors=[".objekt", ".property-item", "article", ".card"],
    )


def scrape_brimo():
    return _generic_static_scrape(
        "BRIMO Allgäu",
        "https://allgaeu-immobilie.de/",
        card_selectors=[".objekt", ".property-item", "article", ".card"],
    )


def scrape_herzstuben():
    return _generic_static_scrape(
        "Herzstuben Immobilien",
        "https://herzstuben.de/",
        card_selectors=[".objekt", ".property-item", "article", ".card"],
    )


STATIC_SCRAPERS = [
    scrape_ohne_makler,
    scrape_vr_bank,  # scrapt nichts mehr, siehe Docstring - liefert nur Hinweis-Link
    scrape_sozialbau,
    scrape_hold_immobilien,
    scrape_brimo,
    scrape_herzstuben,
]
# Sparkasse braucht Playwright (JS-Rendering) - siehe scrape_sparkasse_allgaeu()


# ----------------------------------------------------------------------
# PLAYWRIGHT-SCRAPER (JavaScript-Seiten: ImmoScout24, Immowelt, Kleinanzeigen)
# ----------------------------------------------------------------------

def _generic_playwright_scrape(source_name, url, card_selector, wait_selector=None,
                                price_regex=r'([\d\.]{4,})\s*€'):
    items = []
    error = None
    if not PLAYWRIGHT_AVAILABLE:
        log_scrape(source_name, 0, "Playwright nicht installiert (pip install playwright && playwright install chromium)")
        return items

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=HEADERS["User-Agent"], locale="de-DE")
            page = context.new_page()
            page.goto(url, timeout=25000, wait_until="domcontentloaded")

            # Cookie-Banner best-effort wegklicken (Selektoren variieren stark je Seite)
            for txt in ["Alle akzeptieren", "Akzeptieren", "Zustimmen", "Einverstanden"]:
                try:
                    page.get_by_text(txt, exact=False).first.click(timeout=2000)
                    break
                except Exception:
                    pass

            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=10000)
                except Exception:
                    pass
            else:
                page.wait_for_timeout(3000)

            cards = page.query_selector_all(card_selector)
            for card in cards:
                text = card.inner_text().strip()
                if "€" not in text:
                    continue
                if not in_region(text):
                    continue

                link_el = card.query_selector("a")
                link = link_el.get_attribute("href") if link_el else None
                if not link:
                    continue
                if not link.startswith("http"):
                    base = "/".join(url.split("/")[:3])
                    link = base + (link if link.startswith("/") else "/" + link)

                price = extract_number(text, price_regex, default=None)
                rooms = extract_number(text, r'([\d,]+)\s*Zi', default=None)
                area = extract_number(text, r'([\d,\.]+)\s*m²', default=None)

                if price is None:
                    continue

                title = text.split("\n")[0][:100]

                items.append({
                    "id": f"{source_name.lower().replace(' ', '_')}_{abs(hash(link))}",
                    "title": title,
                    "price": price,
                    "rooms": rooms,
                    "area": area,
                    "location": "Kempten & Umland (20km)",
                    "url": link,
                    "source": source_name,
                })
            browser.close()
    except Exception:
        error = traceback.format_exc(limit=2)

    log_scrape(source_name, len(items), error)
    polite_sleep()
    return items


def scrape_immoscout24():
    # Ort-ID / Radius-Parameter ggf. anpassen: geografischeId & radius in der URL
    # findest du, indem du auf immobilienscout24.de manuell "Kempten (Allgäu)"
    # + 20km Umkreis suchst und die resultierende URL kopierst.
    url = ("https://www.immobilienscout24.de/Suche/de/bayern/kempten-allgaeu/"
           "wohnung-kaufen?radius=20")
    return _generic_playwright_scrape(
        "ImmoScout24", url,
        card_selector="article[data-item='result']",
        wait_selector="article[data-item='result']",
    )


def scrape_immowelt():
    url = "https://www.immowelt.de/liste/kempten-allgau/wohnungen/kaufen?d=true&r=20"
    return _generic_playwright_scrape(
        "Immowelt", url,
        card_selector="[data-testid='serp-card']",
        wait_selector="[data-testid='serp-card']",
    )


def scrape_kleinanzeigen():
    url = "https://www.kleinanzeigen.de/s-wohnung-kaufen/kempten/c196l7586r20"
    return _generic_playwright_scrape(
        "Kleinanzeigen", url,
        card_selector="article.aditem",
        wait_selector="article.aditem",
    )


PLAYWRIGHT_SCRAPERS = [
    scrape_immoscout24,
    scrape_immowelt,
    scrape_kleinanzeigen,
    scrape_sparkasse_allgaeu,
]


# ----------------------------------------------------------------------
# ORCHESTRIERUNG
# ----------------------------------------------------------------------

def scrape_all_sources(include_playwright=True):
    all_found = []
    for fn in STATIC_SCRAPERS:
        try:
            all_found.extend(fn())
        except Exception:
            log_scrape(fn.__name__, 0, traceback.format_exc(limit=2))

    if include_playwright:
        for fn in PLAYWRIGHT_SCRAPERS:
            try:
                all_found.extend(fn())
            except Exception:
                log_scrape(fn.__name__, 0, traceback.format_exc(limit=2))

    return all_found


def save_to_db(items):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    today = datetime.date.today().isoformat()

    new_count = 0
    for item in items:
        try:
            c.execute('''
                INSERT INTO immobilien (id, title, price, rooms, area, location, url, source, first_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (item['id'], item['title'], item['price'], item.get('rooms'), item.get('area'),
                  item['location'], item['url'], item['source'], today))
            new_count += 1
        except sqlite3.IntegrityError:
            c.execute('''
                UPDATE immobilien
                SET title=?, price=?, rooms=?, area=?, location=?, url=?, source=?
                WHERE id=?
            ''', (item['title'], item['price'], item.get('rooms'), item.get('area'),
                  item['location'], item['url'], item['source'], item['id']))
    conn.commit()
    conn.close()
    return new_count


# ----------------------------------------------------------------------
# DASHBOARD
# ----------------------------------------------------------------------

def run_dashboard():
    st.set_page_config(page_title="Immo-Aggregator Kempten +20km", layout="wide")
    st.title("🏡 Immo-Aggregator Kempten & Umland (+20 km)")
    st.caption("Kleinanzeigen, ImmoScout24, Immowelt, Sparkasse, VR Bank, Sozialbau & regionale Makler")

    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM immobilien", conn)
    try:
        log_df = pd.read_sql_query("SELECT * FROM scrape_log", conn)
    except Exception:
        log_df = pd.DataFrame()
    conn.close()

    st.sidebar.header("Filter & Steuerung")

    include_playwright = st.sidebar.checkbox(
        "Große Portale einbeziehen (ImmoScout24/Immowelt/Kleinanzeigen, braucht Playwright)",
        value=PLAYWRIGHT_AVAILABLE, disabled=not PLAYWRIGHT_AVAILABLE)
    if not PLAYWRIGHT_AVAILABLE:
        st.sidebar.warning("Playwright nicht installiert: `pip install playwright` + `playwright install chromium`")

    if st.sidebar.button("🔄 Alle Quellen neu laden"):
        with st.spinner("Sammle aktuelle Angebote... (kann 1-2 Minuten dauern)"):
            items = scrape_all_sources(include_playwright=include_playwright)
            save_to_db(items)
            st.sidebar.success(f"{len(items)} Angebote gefunden & gespeichert!")
            st.rerun()

    if st.sidebar.button("🗑️ Datenbank komplett zurücksetzen"):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM immobilien")
        conn.commit()
        conn.close()
        st.sidebar.warning("Datenbank geleert!")
        st.rerun()

    with st.sidebar.expander("⚙️ Status letzter Scrape-Lauf (zum Debuggen)"):
        if not log_df.empty:
            st.dataframe(log_df, use_container_width=True, hide_index=True)
        else:
            st.write("Noch keine Läufe protokolliert.")

    max_price = st.sidebar.slider("Max. Kaufpreis (€)", 100000, 800000, 500000, step=10000)
    min_rooms = st.sidebar.number_input("Mindestanzahl Zimmer (0 = egal)", min_value=0.0, value=0.0, step=0.5)

    if not df.empty:
        # Hinweis-Einträge ohne Preis (z.B. VR Bank robots.txt-Hinweis) immer anzeigen,
        # sonst nach Preis filtern
        filtered_df = df[df['price'].isna() | (df['price'] <= max_price)]
        if min_rooms > 0:
            filtered_df = filtered_df[filtered_df['rooms'].fillna(0) >= min_rooms]

        col1, col2, col3 = st.columns(3)
        col1.metric("Angebote im System", len(df))
        col2.metric("Nach Filter angezeigt", len(filtered_df))
        col3.metric("Ø-Preis", f"{filtered_df['price'].mean():,.0f} €" if not filtered_df.empty else "N/A")

        st.markdown("---")

        for idx, row in filtered_df.sort_values("price").iterrows():
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                c1.markdown(f"**[{row['title']}]({row['url']})**  \n📍 {row['location']} | Quelle: **{row['source']}**")
                price_txt = f"{row['price']:,.0f} €" if pd.notna(row['price']) else "siehe Portal"
                c2.markdown(f"**Preis:** {price_txt}")
                rooms_txt = f"{row['rooms']:.1f}" if pd.notna(row['rooms']) else "?"
                area_txt = f"{row['area']:.0f}" if pd.notna(row['area']) else "?"
                c3.markdown(f"**Zimmer:** {rooms_txt} | **Fläche:** {area_txt} m²")
                c4.markdown(f"[🔗 Öffnen]({row['url']})")
                st.divider()
    else:
        st.info("Klicke in der Sidebar auf 'Alle Quellen neu laden'.")


if __name__ == "__main__":
    init_db()
    run_dashboard()
