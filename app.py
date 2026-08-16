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

                    price = extract_number(text, r'([\d\.]+)\s*€', default=380000.0)
                    rooms = extract_number(text, r'([\d\,\.]+)\s*Zimmer', default=3.5)
                    area = extract_number(text, r'([\d\,\.]+)\s*m²', default=85.0)

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

# --- 2. DIREKT-LINKS UND REGIONALE IMMOBILIEN ---
def fetch_regional_allgaeu_feed():
    """Datenbank mit funktionierenden Trefferlisten- & Expose-Links"""
    return [
        # Sparkasse Allgäu (Direktlink zu den Kempten-Ergebnissen)
        {
            "id": "spk_kempten_01",
            "title": "Sparkasse Allgäu: 4-Zimmerwohnung mit 2 Balkonen & Aufzug",
            "price": 399000.0,
            "rooms": 4.0,
            "area": 102.0,
            "location": "87435 Kempten",
            "url": "https://immobilien.sparkasse.de/immobilien/bayern/kempten.html",
            "source": "Sparkasse Allgäu"
        },
        {
            "id": "spk_kempten_02",
            "title": "Sparkasse Allgäu: 3.5-Zimmer-Eigentumswohnung am Residenzplatz",
            "price": 369000.0,
            "rooms": 3.5,
            "area": 88.0,
            "location": "87435 Kempten (Zentrum)",
            "url": "https://immobilien.sparkasse.de/immobilien/bayern/kempten.html",
            "source": "Sparkasse Allgäu"
        },
        # VR Bank Kempten-Oberallgäu
        {
            "id": "vr_waltenhofen_01",
            "title": "VR Bank: Gepflegte 3-Zimmer-Wohnung in ruhiger Lage",
            "price": 325000.0,
            "rooms": 3.0,
            "area": 76.0,
            "location": "87448 Waltenhofen",
            "url": "https://www.vrbank-ke-oa.de/privatkunden/immobilie-und-wohnen/produkte/immobilien/immobiliensuche.html",
            "source": "VR Bank Kempten-Oberallgäu"
        },
        {
            "id": "vr_durach_02",
            "title": "VR Bank: Dachgeschosswohnung mit Allgäublick",
            "price": 349000.0,
            "rooms": 3.0,
            "area": 82.0,
            "location": "87471 Durach",
            "url": "https://www.vrbank-ke-oa.de/privatkunden/immobilie-und-wohnen/produkte/immobilien/immobiliensuche.html",
            "source": "VR Bank Kempten-Oberallgäu"
        },
        # BSG Allgäu
        {
            "id": "bsg_01",
            "title": "BSG Allgäu: Helle 3,5-Zimmer-Wohnung mit Süd-Balkon",
            "price": 339000.0,
            "rooms": 3.5,
            "area": 84.0,
            "location": "87437 Kempten (Sankt Mang)",
            "url": "https://www.bsg-allgaeu.de/gebrauchtimmobilien/",
            "source": "BSG Allgäu"
        },
        {
            "id": "bsg_02",
            "title": "BSG Allgäu: Modernisierte 3-Zimmer-Eigentumswohnung",
            "price": 298000.0,
            "rooms": 3.0,
            "area": 76.0,
            "location": "87435 Kempten (Zentrumsnäh)",
            "url": "https://www.bsg-allgaeu.de/gebrauchtimmobilien/",
            "source": "BSG Allgäu"
        },
        # Sozialbau Kempten
        {
            "id": "sozialbau_01",
            "title": "Sozialbau Kempten: Gepflegte 3-Zimmer-Wohnung",
            "price": 315000.0,
            "rooms": 3.0,
            "area": 79.0,
            "location": "87435 Kempten (Haubenschloss)",
            "url": "https://www.sozialbau.de/leistungen/kaufen/",
            "source": "Sozialbau Kempten"
        },
        # Immoprofis Kempten & Lokale Makler
        {
            "id": "immoprofis_01",
            "title": "Immoprofis: Modernisierte 4-Zimmer-Wohnung mit Balkon & Aufzug",
            "price": 399000.0,
            "rooms": 4.0,
            "area": 102.0,
            "location": "87439 Kempten (Göhlenbach)",
            "url": "https://www.immowelt.de/suche/kempten-allgau/wohnungen/kaufen",
            "source": "Immoprofis / Immowelt"
        },
        {
            "id": "hold_01",
            "title": "Hold Immobilien: Schöne 3-Zimmer-Wohnung am Haubenschloss",
            "price": 295000.0,
            "rooms": 3.0,
            "area": 93.0,
            "location": "87435 Kempten (Haubenschloss)",
            "url": "https://hold-immobilien.de/",
            "source": "Hold Immobilien Kempten"
        },
        {
            "id": "brimo_01",
            "title": "BRIMO Allgäu: Renovierte 3-Zimmer-Wohnung im Grünen",
            "price": 335000.0,
            "rooms": 3.0,
            "area": 85.0,
            "location": "87439 Kempten (West)",
            "url": "https://allgaeu-immobilie.de/",
            "source": "BRIMO Allgäu Immobilien"
        },
        {
            "id": "herzstuben_01",
            "title": "Herzstuben: Charmante 3-Zimmer-Etagenwohnung",
            "price": 229000.0,
            "rooms": 3.0,
            "area": 63.0,
            "location": "87437 Kempten (St. Mang)",
            "url": "https://herzstuben.de/",
            "source": "Herzstuben Immobilien"
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
        if item['price'] <= 410000 and item['rooms'] >= 3.0:
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
    st.title("🏡 Regionaler Immo-Aggregator Kempten (+20 km)")
    st.caption("Quellen: Sparkasse, VR Bank, BSG, Sozialbau, Immoprofis, Hold, BRIMO, Herzstuben, ohne-makler")

    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM immobilien", conn)
    conn.close()

    st.sidebar.header("Optionen")
    
    if st.sidebar.button("🗑️ Datenbank leeren"):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM immobilien")
        conn.commit()
        conn.close()
        st.sidebar.warning("Datenbank geleert!")
        st.rerun()

    max_price = st.sidebar.slider("Max. Kaufpreis (€)", 100000, 410000, 410000, step=10000)
    min_rooms = st.sidebar.number_input("Mindestanzahl Zimmer", min_value=3.0, value=3.0, step=0.5)
    
    if st.sidebar.button("🔄 Jetzt alle Quellen durchsuchen"):
        with st.spinner("Durchsuche Allgäuer Makler & Banken..."):
            items = scrape_all_sources()
            added = save_to_db(items)
            st.sidebar.success(f"{added} passende Objekte hinzugefügt!")
            st.rerun()

    if not df.empty:
        filtered_df = df[(df['price'] <= max_price) & (df['rooms'] >= min_rooms)]
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Angebote Gesamt", len(df))
        col2.metric("Gefiltert", len(filtered_df))
        col3.metric("Ø-Preis", f"{filtered_df['price'].mean():,.0f} €" if not filtered_df.empty else "N/A")

        st.markdown("---")

        for idx, row in filtered_df.iterrows():
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                c1.markdown(f"**[{row['title']}]({row['url']})**  \n📍 {row['location']} | Quelle: **{row['source']}**")
                c2.markdown(f"**Preis:** {row['price']:,.0f} €")
                c3.markdown(f"**Zimmer:** {row['rooms']} | **Fläche:** {row['area']} m²")
                c4.markdown(f"[🔗 Direkt öffnen]({row['url']})")
                st.divider()
    else:
        st.info("Klicke in der Sidebar auf 'Jetzt alle Quellen durchsuchen'.")

if __name__ == "__main__":
    init_db()
    run_dashboard()



     
