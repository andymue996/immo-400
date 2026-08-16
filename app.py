import sqlite3
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st
import datetime
import re

DB_NAME = "kempten_immobilien.db"

# Header für Web-Requests (verhindert einfaches Blockieren)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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

# --- 1. REGIONALE PRIVATPORTALE (ohne-makler.net) ---
def scrape_ohne_makler():
    items = []
    url = "https://www.ohne-makler.net/immobilien/kauf/bayern/oberallgaeu-kempten/"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            cards = soup.select(".om-estate-card, article, .row.estate")
            for card in cards:
                title_elem = card.find(["h2", "h3", "h4"])
                if not title_elem:
                    continue
                title = title_elem.get_text(strip=True)
                
                link_elem = card.find("a")
                link = ""
                if link_elem and link_elem.get("href"):
                    link = link_elem["href"]
                    if not link.startswith("http"):
                        link = "https://www.ohne-makler.net" + link
                
                text_content = card.get_text()
                price = extract_number(text_content, r'([\d\.]+)\s*€', default=350000.0)
                rooms = extract_number(text_content, r'([\d\,\.]+)\s*Zimmer', default=3.0)
                area = extract_number(text_content, r'([\d\,\.]+)\s*m²', default=75.0)

                item_id = f"om_{hash(link if link else title)}"
                items.append({
                    "id": item_id,
                    "title": title,
                    "price": price,
                    "rooms": rooms,
                    "area": area,
                    "location": "Kempten & Umland (Allgäu)",
                    "url": link or "https://www.ohne-makler.net",
                    "source": "ohne-makler.net"
                })
    except Exception as e:
        print(f"Fehler bei ohne-makler: {e}")
    return items

# --- 2. SPARKASSE ALLGÄU ---
def scrape_sparkasse():
    items = []
    # Öffentliche Landingpage der Sparkasse für Kempten/Oberallgäu Kaufobjekte
    url = "https://immobilien.sparkasse.de/immobilien/bayern/kempten.html"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            # Durchsuche Inserate-Karten der Sparkasse
            cards = soup.select(".estate-card, .immo-card, .result-item, article")
            for card in cards:
                title_elem = card.find(["h2", "h3", "a"])
                if not title_elem:
                    continue
                title = title_elem.get_text(strip=True)
                
                link_elem = card.find("a")
                link = link_elem["href"] if link_elem and link_elem.get("href") else url
                if not link.startswith("http"):
                    link = "https://immobilien.sparkasse.de" + link
                    
                text_content = card.get_text()
                price = extract_number(text_content, r'Kaufpreis\s*([\d\.]+)\s*€', default=380000.0)
                rooms = extract_number(text_content, r'([\d\,\.]+)\s*Zi', default=3.0)
                area = extract_number(text_content, r'([\d\,\.]+)\s*m²', default=80.0)
                
                items.append({
                    "id": f"spk_{hash(link)}",
                    "title": f"[Sparkasse] {title}",
                    "price": price,
                    "rooms": rooms,
                    "area": area,
                    "location": "Raum Kempten (Allgäu)",
                    "url": link,
                    "source": "Sparkasse Allgäu"
                })
    except Exception as e:
        print(f"Fehler bei Sparkasse Allgäu: {e}")
    return items

# --- 3. VR BANK KEMPTEN / GENOSSENSCHAFTSBANKEN ---
def scrape_vrbank():
    items = []
    # Öffentliche Suche der VR-Banken im Allgäu
    url = "https://www.vr.de/privatkunden/immobilien/immobiliensuche.html"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            cards = soup.select(".immo-item, .search-result, article")
            for card in cards:
                text_content = card.get_text()
                # Nur Angebote aus Bayern / Allgäu / Kempten filtern
                if "Kempten" in text_content or "Allgäu" in text_content or "874" in text_content:
                    title_elem = card.find(["h2", "h3", "a"])
                    title = title_elem.get_text(strip=True) if title_elem else "VR Bank Immobilienangebot"
                    
                    link_elem = card.find("a")
                    link = link_elem["href"] if link_elem and link_elem.get("href") else url
                    
                    price = extract_number(text_content, r'([\d\.]+)\s*€', default=390000.0)
                    rooms = extract_number(text_content, r'([\d\,\.]+)\s*Zimmer', default=3.0)
                    area = extract_number(text_content, r'([\d\,\.]+)\s*m²', default=85.0)

                    items.append({
                        "id": f"vr_{hash(link)}",
                        "title": f"[VR Bank] {title}",
                        "price": price,
                        "rooms": rooms,
                        "area": area,
                        "location": "Kempten & Umkreis (+20 km)",
                        "url": link,
                        "source": "VR Bank Kempten-Oberallgäu"
                    })
    except Exception as e:
        print(f"Fehler bei VR Bank: {e}")
    return items

# Hilfsfunktion zur Zahlensuche
def extract_number(text, regex_pattern, default=0.0):
    match = re.search(regex_pattern, text, re.IGNORECASE)
    if match:
        try:
            val_str = match.group(1).replace(".", "").replace(",", ".")
            return float(val_str)
        except:
            pass
    return default

def scrape_all_sources():
    all_found = []
    all_found.extend(scrape_ohne_makler())
    all_found.extend(scrape_sparkasse())
    all_found.extend(scrape_vrbank())
    return all_found

def save_to_db(items):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    today = datetime.date.today().isoformat()
    
    new_count = 0
    for item in items:
        # Filter: Max. 410.000 € Kaufpreis (damit inklusive Nebenkosten <= 450.000 €) & min. 3 Zimmer
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
    st.caption("Quellen: Sparkasse Allgäu, VR Bank, ohne-makler.net | Mind. 3 Zimmer | Max. 410.000 € Kaufpreis")

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
        st.sidebar.warning("Datenbank zurückgesetzt!")
        st.rerun()

    max_price = st.sidebar.slider("Max. Kaufpreis (€)", 100000, 410000, 410000, step=10000)
    min_rooms = st.sidebar.number_input("Mindestanzahl Zimmer", min_value=3.0, value=3.0, step=0.5)
    
    if st.sidebar.button("🔄 Jetzt alle Banken & Portale durchsuchen"):
        with st.spinner("Scrape Sparkasse Allgäu, VR Bank & regionale Portale..."):
            items = scrape_all_sources()
            added = save_to_db(items)
            st.sidebar.success(f"{added} neue passende Objekte hinzugefügt!")
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
                c4.markdown(f"*Gefunden: {row['first_seen']}*")
                st.divider()
    else:
        st.info("Klicke in der Sidebar auf 'Jetzt alle Banken & Portale durchsuchen'.")

if __name__ == "__main__":
    init_db()
    run_dashboard()
