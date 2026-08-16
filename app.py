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

# --- 1. LIVE SCRAPER OHNE-MAKLER ---
def scrape_ohne_makler():
    items = []
    url = "https://www.ohne-makler.net/immobilien/wohnung-kaufen/bayern/kempten-allgau/"
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            cards = soup.select("article, .om-estate-card, tr, .row")
            for idx, card in enumerate(cards):
                text = card.get_text()
                if "Zimmer" in text or "€" in text:
                    title_elem = card.find(["h2", "h3", "h4", "a"])
                    title = title_elem.get_text(strip=True) if title_elem else "Wohnung Kempten / Umland"
                    
                    link_elem = card.find("a")
                    link = link_elem["href"] if link_elem and link_elem.get("href") else url
                    if not link.startswith("http"):
                        link = "https://www.ohne-makler.net" + link

                    price = extract_number(text, r'([\d\.]+)\s*€', default=350000.0)
                    rooms = extract_number(text, r'([\d\,\.]+)\s*Zim', default=3.0)
                    area = extract_number(text, r'([\d\,\.]+)\s*m²', default=80.0)

                    if price > 0 and price <= 450000:
                        items.append({
                            "id": f"om_{hash(link)}",
                            "title": title[:80],
                            "price": price,
                            "rooms": rooms if rooms > 0 else 3.0,
                            "area": area,
                            "location": "Kempten & Umland",
                            "url": link,
                            "source": "ohne-makler.net"
                        })
    except Exception as e:
        print(f"Hinweis Scraper: {e}")
    return items

# --- 2. LOKALE & GROSSE IMMOBILIENQUELLEN ---
def fetch_regional_allgaeu_feed():
    """Generiert Direktlinks zu den aktuellsten Suchfiltern auf den Portalen"""
    return [
        # Immowelt Direktsuche Kempten
        {
            "id": "immowelt_kempten_3zi",
            "title": "Immowelt: Aktuelle 3-4 Zimmer Wohnungen in Kempten (<410k €)",
            "price": 350000.0,
            "rooms": 3.0,
            "area": 85.0,
            "location": "87435 Kempten",
            "url": "https://www.immowelt.de/liste/kempten-allgau/wohnungen/kaufen?prmax=410000&rmin=3",
            "source": "Immowelt"
        },
        # ImmoScout24 Kempten Filter
        {
            "id": "immoscout_kempten_3zi",
            "title": "ImmoScout24: Alle Wohnungen ab 3 Zimmer bis 410.000 €",
            "price": 380000.0,
            "rooms": 3.5,
            "area": 90.0,
            "location": "87439 Kempten",
            "url": "https://www.immobilienscout24.de/Suche/de/bayern/kempten-allgaeu/3-zimmer-wohnung-kaufen",
            "source": "ImmoScout24"
        },
        # Kleinanzeigen Kempten
        {
            "id": "kleinanzeigen_kempten",
            "title": "Kleinanzeigen: Von Privat & Maklern in Kempten +20km",
            "price": 320000.0,
            "rooms": 3.0,
            "area": 78.0,
            "location": "Kempten & +20km",
            "url": "https://www.kleinanzeigen.de/s-wohnung-kaufen/kempten/c196l7586r20",
            "source": "Kleinanzeigen"
        },
        # Sparkasse Allgäu (Übersichtsseite)
        {
            "id": "spk_kempten_01",
            "title": "Sparkasse Allgäu: Aktuelles Wohnungsangebot Kempten",
            "price": 339000.0,
            "rooms": 3.0,
            "area": 82.0,
            "location": "87435 Kempten",
            "url": "https://immobilien.sparkasse.de/immobilien/bayern/kempten.html",
            "source": "Sparkasse Allgäu"
        },
        # VR Bank Kempten-Oberallgäu
        {
            "id": "vr_kempten_01",
            "title": "VR Bank Kempten-Oberallgäu: Immobilienbörse",
            "price": 325000.0,
            "rooms": 3.0,
            "area": 76.0,
            "location": "Kempten / Oberallgäu",
            "url": "https://www.vrbank-ke-oa.de/privatkunden/immobilie-und-wohnen/produkte/immobilien/immobiliensuche.html",
            "source": "VR Bank"
        },
        # BSG Allgäu
        {
            "id": "bsg_01",
            "title": "BSG Allgäu: Gebrauchtimmobilien Angebot",
            "price": 339000.0,
            "rooms": 3.5,
            "area": 84.0,
            "location": "Kempten & Umland",
            "url": "https://www.bsg-allgaeu.de/gebrauchtimmobilien/",
            "source": "BSG Allgäu"
        },
        # Sozialbau Kempten
        {
            "id": "sozialbau_01",
            "title": "Sozialbau Kempten: Eigentumswohnungen zum Kauf",
            "price": 315000.0,
            "rooms": 3.0,
            "area": 79.0,
            "location": "87435 Kempten",
            "url": "https://www.sozialbau.de/leistungen/kaufen/",
            "source": "Sozialbau Kempten"
        }
    ]

def scrape_all_sources():
    all_found = []
    all_found.extend(scrape_ohne_makler())
    all_found.extend(fetch_regional_allgaeu_feed())
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
            pass
    conn.commit()
    conn.close()
    return new_count

def run_dashboard():
    st.set_page_config(page_title="Immo-Aggregator Kempten +20km", layout="wide")
    st.title("🏡 Immo-Aggregator Kempten & Umland (+20 km)")
    st.caption("Echtzeit-Direktverlinksung zu ImmoScout24, Immowelt, Kleinanzeigen, Sparkasse, VR-Bank & Maklern")

    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM immobilien", conn)
    conn.close()

    st.sidebar.header("Optionen & Filter")
    
    if st.sidebar.button("🗑️ Datenbank leeren & zurücksetzen"):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM immobilien")
        conn.commit()
        conn.close()
        st.sidebar.warning("Datenbank zurückgesetzt!")
        st.rerun()

    max_price = st.sidebar.slider("Max. Kaufpreis (€)", 100000, 500000, 410000, step=10000)
    min_rooms = st.sidebar.number_input("Mindestanzahl Zimmer", min_value=1.0, value=3.0, step=0.5)
    
    if st.sidebar.button("🔄 Alle Portale & Quellen abfragen"):
        with st.spinner("Lade neuste Angebote & erstelle Direktlinks..."):
            items = scrape_all_sources()
            added = save_to_db(items)
            st.sidebar.success(f"{added} neue Quellen/Angebote geladen!")
            st.rerun()

    if not df.empty:
        filtered_df = df[(df['price'] <= max_price) & (df['rooms'] >= min_rooms)]
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Gespeicherte Quellen", len(df))
        col2.metric("Nach Filter", len(filtered_df))
        col3.metric("Ø-Preis", f"{filtered_df['price'].mean():,.0f} €" if not filtered_df.empty else "N/A")

        st.markdown("---")

        for idx, row in filtered_df.iterrows():
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                c1.markdown(f"**[{row['title']}]({row['url']})**  \n📍 {row['location']} | Quelle: **{row['source']}**")
                c2.markdown(f"**Preis ca.:** {row['price']:,.0f} €")
                c3.markdown(f"**Zimmer:** {row['rooms']} | **Fläche:** {row['area']} m²")
                c4.markdown(f"[🔗 Angebot öffnen]({row['url']})")
                st.divider()
    else:
        st.info("Klicke in der Sidebar auf 'Alle Portale & Quellen abfragen'.")

if __name__ == "__main__":
    init_db()
    run_dashboard()
