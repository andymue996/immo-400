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
            is_portal_link INTEGER DEFAULT 0,
            first_seen DATE
        )
    ''')
    conn.commit()
    conn.close()

def extract_num(text, pattern):
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1).replace(".", "").replace(",", "."))
        except:
            pass
    return 0.0

# --- REALER LIVE-SCRAPER (ohne-makler.net) ---
def scrape_ohne_makler():
    items = []
    url = "https://www.ohne-makler.net/immobilien/bayern/kempten-allgau/"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            # Suche nach allen Links/Containern mit Preisen
            text_blocks = soup.find_all(["div", "li", "article"])
            for block in text_blocks:
                text = block.get_text(separator=" ")
                if "€" in text and ("Zimmer" in text or "m²" in text):
                    title_elem = block.find(["h2", "h3", "a"])
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    if len(title) < 10 or "Provisionsfreie" in title:
                        continue

                    link_elem = block.find("a")
                    link = link_elem["href"] if link_elem and link_elem.get("href") else url
                    if not link.startswith("http"):
                        link = "https://www.ohne-makler.net" + link

                    price = extract_num(text, r'([\d\.]+)\s*€')
                    rooms = extract_num(text, r'([\d\,\.]+)\s*Zi')
                    if rooms == 0:
                        rooms = extract_num(text, r'([\d\,\.]+)\s*Zimmer')
                    area = extract_num(text, r'([\d\,\.]+)\s*m²')

                    if price > 50000 and rooms > 0:
                        items.append({
                            "id": f"om_{hash(link)}",
                            "title": title[:90],
                            "price": price,
                            "rooms": rooms,
                            "area": area,
                            "location": "Kempten & Umland",
                            "url": link,
                            "source": "ohne-makler.net",
                            "is_portal_link": 0
                        })
    except Exception as e:
        print(f"Scraper-Fehler: {e}")
    return items

# --- DIREKTLINKS ZU LOKALEN MAKLERN ---
def fetch_portal_links():
    return [
        {
            "id": "link_spk_kempten",
            "title": "Sparkasse Allgäu — Kaufangebote Kempten",
            "price": 0.0, "rooms": 0.0, "area": 0.0,
            "location": "87435 Kempten",
            "url": "https://immobilien.sparkasse.de/immobilien/bayern/kempten.html",
            "source": "Sparkasse Allgäu",
            "is_portal_link": 1
        },
        {
            "id": "link_vr_kempten",
            "title": "VR Bank Kempten-Oberallgäu — Immobiliensuche",
            "price": 0.0, "rooms": 0.0, "area": 0.0,
            "location": "Kempten & Umland",
            "url": "https://www.vrbank-ke-oa.de/privatkunden/immobilie-und-wohnen/produkte/immobilien/immobiliensuche.html",
            "source": "VR Bank",
            "is_portal_link": 1
        },
        {
            "id": "link_bsg_allgaeu",
            "title": "BSG Allgäu — Gebrauchtimmobilien",
            "price": 0.0, "rooms": 0.0, "area": 0.0,
            "location": "87437 Kempten",
            "url": "https://www.bsg-allgaeu.de/gebrauchtimmobilien/",
            "source": "BSG Allgäu",
            "is_portal_link": 1
        },
        {
            "id": "link_sozialbau",
            "title": "Sozialbau Kempten — Kaufen",
            "price": 0.0, "rooms": 0.0, "area": 0.0,
            "location": "87435 Kempten",
            "url": "https://www.sozialbau.de/leistungen/kaufen/",
            "source": "Sozialbau Kempten",
            "is_portal_link": 1
        },
        {
            "id": "link_michael_beck",
            "title": "Michael Beck Immobilien — Aktuelle Kaufobjekte",
            "price": 0.0, "rooms": 0.0, "area": 0.0,
            "location": "87439 Kempten",
            "url": "https://beckimmobilien.de/kaufen/",
            "source": "Michael Beck Immobilien",
            "is_portal_link": 1
        },
        {
            "id": "link_walter_beck",
            "title": "Walter Beck Immobilien — Angebotsübersicht",
            "price": 0.0, "rooms": 0.0, "area": 0.0,
            "location": "87435 Kempten",
            "url": "https://www.immobilienbeck.de/aktuelleobjekte/",
            "source": "Walter Beck Immobilien",
            "is_portal_link": 1
        },
        {
            "id": "link_kleinanzeigen",
            "title": "Kleinanzeigen — Immobilien Kempten (+20km)",
            "price": 0.0, "rooms": 0.0, "area": 0.0,
            "location": "Kempten + 20km",
            "url": "https://www.kleinanzeigen.de/s-wohnung-kaufen/kempten/c196l7586r20",
            "source": "Kleinanzeigen",
            "is_portal_link": 1
        }
    ]

def save_to_db(items):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    today = datetime.date.today().isoformat()
    
    for item in items:
        c.execute('''
            INSERT OR REPLACE INTO immobilien (id, title, price, rooms, area, location, url, source, is_portal_link, first_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (item['id'], item['title'], item['price'], item['rooms'], item['area'], item['location'], item['url'], item['source'], item['is_portal_link'], today))
    conn.commit()
    conn.close()

def run_dashboard():
    st.set_page_config(page_title="Immo-Aggregator Kempten", layout="wide")
    st.title("🏡 Immo-Aggregator Kempten (+20 km)")

    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM immobilien", conn)
    conn.close()

    st.sidebar.header("Filter für Live-Angebote")
    max_price = st.sidebar.slider("Max. Kaufpreis (€)", 100000, 600000, 450000, step=10000)
    min_rooms = st.sidebar.number_input("Mindestanzahl Zimmer", min_value=1.0, value=2.0, step=0.5)
    
    if st.sidebar.button("🔄 Jetzt Daten aktualisieren"):
        with st.spinner("Durchsuche Quellen..."):
            items = scrape_ohne_makler() + fetch_portal_links()
            save_to_db(items)
            st.sidebar.success("Aktualisiert!")
            st.rerun()

    tab1, tab2 = st.tabs(["🔎 Live-Angebote", "🌐 Lokale Makler & Portale"])

    if not df.empty:
        # Live Angebote
        live_df = df[df['is_portal_link'] == 0]
        filtered_live = live_df[(live_df['price'] <= max_price) & (live_df['rooms'] >= min_rooms)]
        
        with tab1:
            st.caption(f"{len(filtered_live)} passende Live-Angebote gefunden")
            if not filtered_live.empty:
                for idx, row in filtered_live.iterrows():
                    with st.container():
                        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                        c1.markdown(f"**[{row['title']}]({row['url']})**  \n📍 {row['location']} | Quelle: {row['source']}")
                        c2.markdown(f"**Preis:** {row['price']:,.0f} €")
                        c3.markdown(f"**Zimmer:** {row['rooms']} | **Fläche:** {row['area']} m²")
                        c4.markdown(f"[🔗 Link öffnen]({row['url']})")
                        st.divider()
            else:
                st.info("Keine Angebote im gewählten Preis-/Zimmerfilter vorhanden.")

        # Direktlinks
        portal_df = df[df['is_portal_link'] == 1]
        with tab2:
            st.caption("Direkte Verlinkungen zu den Immobilien-Seiten regionaler Anbieter:")
            for idx, row in portal_df.iterrows():
                with st.container():
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**{row['title']}** ({row['source']})")
                    c2.markdown(f"[🔗 Makler-Seite öffnen]({row['url']})")
                    st.divider()
    else:
        st.info("Klicke in der Sidebar auf 'Jetzt Daten aktualisieren'.")

if __name__ == "__main__":
    init_db()
    run_dashboard()




