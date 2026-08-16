import sqlite3
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st
import datetime
import re

DB_NAME = "kempten_immobilien.db"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

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
    conn.commit()
    conn.close()

def extract_number(text, regex_pattern, default=0.0):
    match = re.search(regex_pattern, text, re.IGNORECASE)
    if match:
        try:
            val_str = match.group(1).replace(".", "").replace(",", ".")
            return float(val_str)
        except:
            pass
    return default

# --- 1. REALES SCRAPING (ohne-makler.net) ---
def scrape_ohne_makler():
    items = []
    url = "https://www.ohne-makler.net/immobilien/kauf/bayern/oberallgaeu-kempten/"
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            cards = soup.select(".om-estate-card, article, .row")
            for idx, card in enumerate(cards):
                text = card.get_text()
                if "Zimmer" in text or "€" in text:
                    title_elem = card.find(["h2", "h3", "h4", "a"])
                    title = title_elem.get_text(strip=True) if title_elem else "Immobilie Kempten / Umland"
                    
                    link_elem = card.find("a")
                    link = link_elem["href"] if link_elem and link_elem.get("href") else url
                    if not link.startswith("http"):
                        link = "https://www.ohne-makler.net" + link

                    price = extract_number(text, r'([\d\.]+)\s*€', default=0.0)
                    rooms = extract_number(text, r'([\d\,\.]+)\s*Zimmer', default=0.0)
                    area = extract_number(text, r'([\d\,\.]+)\s*m²', default=0.0)

                    if price > 0 and rooms > 0:
                        items.append({
                            "id": f"om_{hash(link)}",
                            "title": title[:80],
                            "price": price,
                            "rooms": rooms,
                            "area": area,
                            "location": "Kempten & Umland",
                            "url": link,
                            "source": "ohne-makler.net"
                        })
    except Exception as e:
        print(f"Hinweis Scraper: {e}")
    return items

# --- 2. DIREKTLINKS ZU DEN REGIONALEN MAKLERN ---
def fetch_regional_portals():
    return [
        {
            "id": "link_spk_kempten",
            "title": "Sparkasse Allgäu — Alle Kaufangebote Kempten",
            "price": 0.0,
            "rooms": 0.0,
            "area": 0.0,
            "location": "87435 Kempten",
            "url": "https://immobilien.sparkasse.de/immobilien/bayern/kempten.html",
            "source": "Sparkasse Allgäu"
        },
        {
            "id": "link_vr_kempten",
            "title": "VR Bank Kempten-Oberallgäu — Immobiliensuche",
            "price": 0.0,
            "rooms": 0.0,
            "area": 0.0,
            "location": "87435 Kempten & Umland",
            "url": "https://www.vrbank-ke-oa.de/privatkunden/immobilie-und-wohnen/produkte/immobilien/immobiliensuche.html",
            "source": "VR Bank"
        },
        {
            "id": "link_bsg_allgaeu",
            "title": "BSG Allgäu — Gebrauchtimmobilien Kaufen",
            "price": 0.0,
            "rooms": 0.0,
            "area": 0.0,
            "location": "87437 Kempten",
            "url": "https://www.bsg-allgaeu.de/gebrauchtimmobilien/",
            "source": "BSG Allgäu"
        },
        {
            "id": "link_sozialbau",
            "title": "Sozialbau Kempten — Kaufangebote Übersicht",
            "price": 0.0,
            "rooms": 0.0,
            "area": 0.0,
            "location": "87435 Kempten",
            "url": "https://www.sozialbau.de/leistungen/kaufen/",
            "source": "Sozialbau Kempten"
        },
        {
            "id": "link_michael_beck",
            "title": "Michael Beck Immobilien — Aktuelle Objekte zum Kauf",
            "price": 0.0,
            "rooms": 0.0,
            "area": 0.0,
            "location": "87439 Kempten",
            "url": "https://beckimmobilien.de/kaufen/",
            "source": "Michael Beck Immobilien"
        },
        {
            "id": "link_walter_beck",
            "title": "Walter Beck Immobilien — Angebotsübersicht Kempten",
            "price": 0.0,
            "rooms": 0.0,
            "area": 0.0,
            "location": "87435 Kempten",
            "url": "https://www.immobilienbeck.de/aktuelleobjekte/",
            "source": "Walter Beck Immobilien"
        },
        {
            "id": "link_kleinanzeigen",
            "title": "Kleinanzeigen — Immobilien Kaufen in Kempten (+20km)",
            "price": 0.0,
            "rooms": 0.0,
            "area": 0.0,
            "location": "Kempten + 20km",
            "url": "https://www.kleinanzeigen.de/s-wohnung-kaufen/kempten/c196l7586r20",
            "source": "Kleinanzeigen"
        }
    ]

def scrape_all_sources():
    all_found = []
    all_found.extend(scrape_ohne_makler())
    all_found.extend(fetch_regional_portals())
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
            ''', (item['id'], item['title'], item['price'], item['rooms'], item['area'], item['location'], item['url'], item['source'], today))
            new_count += 1
        except sqlite3.IntegrityError:
            c.execute('''
                UPDATE immobilien 
                SET title=?, price=?, rooms=?, area=?, location=?, url=?, source=?
                WHERE id=?
            ''', (item['title'], item['price'], item['rooms'], item['area'], item['location'], item['url'], item['source'], item['id']))
    conn.commit()
    conn.close()
    return new_count

def run_dashboard():
    st.set_page_config(page_title="Immo-Aggregator Kempten", layout="wide")
    st.title("🏡 Immo-Aggregator & Portal-Radar Kempten (+20 km)")
    st.caption("Live-Angebote von ohne-makler.net + Direkte Links zu lokalen Maklern & Genossenschaften")

    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM immobilien", conn)
    conn.close()

    st.sidebar.header("Optionen & Filter")
    
    if st.sidebar.button("🗑️ Datenbank zurücksetzen"):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM immobilien")
        conn.commit()
        conn.close()
        st.sidebar.warning("Datenbank geleert!")
        st.rerun()

    max_price = st.sidebar.slider("Max. Kaufpreis (€)", 100000, 600000, 420000, step=10000)
    min_rooms = st.sidebar.number_input("Mindestanzahl Zimmer", min_value=1.0, value=3.0, step=0.5)
    
    if st.sidebar.button("🔄 Jetzt Daten aktualisieren"):
        with st.spinner("Lade Angebote & Portallinks..."):
            items = scrape_all_sources()
            added = save_to_db(items)
            st.sidebar.success("Erfolgreich aktualisiert!")
            st.rerun()

    if not df.empty:
        # Unterscheidung zwischen Live-Objekten und Portal-Direktlinks
        live_items = df[df['price'] > 0]
        portal_links = df[df['price'] == 0]

        filtered_live = live_items[(live_items['price'] <= max_price) & (live_items['rooms'] >= min_rooms)]
        
        st.subheader("🔎 Gefundene Einzelobjekte")
        if not filtered_live.empty:
            for idx, row in filtered_live.iterrows():
                with st.container():
                    c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                    c1.markdown(f"**[{row['title']}]({row['url']})**  \n📍 {row['location']} | Quelle: **{row['source']}**")
                    c2.markdown(f"**Preis:** {row['price']:,.0f} €")
                    c3.markdown(f"**Zimmer:** {row['rooms']} | **Fläche:** {row['area']} m²")
                    c4.markdown(f"[🔗 Angebot öffnen]({row['url']})")
                    st.divider()
        else:
            st.info("Keine einzelnen Live-Objekte unter den gewählten Filterkriterien gefunden.")

        st.markdown("---")
        st.subheader("🌐 Direktlinks zu den lokalen Maklern & Portalen")
        st.caption("Aufgrund von Abfagesperren der Makler-Webseiten bieten diese Links den direkten Zugang zu den tagesaktuellen Beständen:")
        
        for idx, row in portal_links.iterrows():
            with st.container():
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"**{row['title']}** ({row['source']})")
                c2.markdown(f"[🔗 Seite öffnen]({row['url']})")
                st.divider()

    else:
        st.info("Klicke in der Sidebar auf 'Jetzt Daten aktualisieren'.")

if __name__ == "__main__":
    init_db()
    run_dashboard()



