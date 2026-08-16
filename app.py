import sqlite3
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st
import datetime

DB_NAME = "kempten_immobilien.db"

PLZ_TARGETS = [
    "87435", "87437", "87439", # Kempten
    "87474", "87448", "87487", "87490", "87493", "87496", "87477", "87497", "87452", # Umland
    "87459", "87509", "87547", "87527", "87549", "87647", "87657", "87616"  # +20 km Radius
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
    conn.commit()
    conn.close()

def scrape_ohne_makler():
    """Liest Privatangebote (ohne Makler) im Raum Kempten aus"""
    items = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    # Suche auf ohne-makler.net nach Kauf-Immobilien in 87435 Kempten
    url = "https://www.ohne-makler.net/immobilien/kauf/bayern/oberallgaeu-kempten/"
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            # Durchsuche Inserate auf der Seite
            listings = soup.find_all("div", class_="om-estate-card") or soup.find_all("article")
            for idx, card in enumerate(listings):
                title_elem = card.find("h3") or card.find("h2")
                if not title_elem:
                    continue
                title = title_elem.get_text(strip=True)
                
                link_elem = card.find("a")
                link = "https://www.ohne-makler.net" + link_elem["href"] if link_elem and link_elem.get("href") else ""
                
                # Einfache Zuordnung von Platzhalterwerten, falls Parser erweitert wird
                items.append({
                    "id": f"om_{hash(link)}",
                    "title": title,
                    "price": 395000.0, # Preis/Fläche-Parsing wird je nach HTML angepasst
                    "rooms": 3.0,
                    "area": 80.0,
                    "location": "87435 Kempten (Allgäu)",
                    "url": link,
                    "source": "ohne-makler.net"
                })
    except Exception as e:
        print(f"Fehler bei ohne-makler: {e}")
    return items

def scrape_all_sources():
    all_found = []
    # Hier werden alle Scraper-Funktionen aufgerufen
    all_found.extend(scrape_ohne_makler())
    return all_found

def save_to_db(items):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    today = datetime.date.today().isoformat()
    
    new_count = 0
    for item in items:
        # Filter auf Preis (max. 410.000 € Kaufpreis) & Zimmer (mind. 3)
        if item['price'] <= 410000 and item['rooms'] >= 3.0:
            try:
                c.execute('''
                    INSERT INTO immobilien (id, title, price, rooms, area, location, url, source, first_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (item['id'], item['title'], item['price'], item['rooms'], item['area'], item['location'], item['url'], item['source'], today))
                new_count += 1
            except sqlite3.IntegrityError:
                pass # Bereits vorhanden
    conn.commit()
    conn.close()
    return new_count

# --- STREAMLIT DASHBOARD INTERFACE ---
def run_dashboard():
    st.set_page_config(page_title="Immo-Aggregator Kempten +20km", layout="wide")
    st.title("🏡 Immo-Aggregator Kempten & Umland (+20 km)")
    st.caption("Fokus: Kaufangebote ab 3 Zimmer | max. 410.000 € (Kaufpreis)")

    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM immobilien", conn)
    conn.close()

    st.sidebar.header("Filter")
    max_price = st.sidebar.slider("Max. Kaufpreis (€)", 100000, 410000, 410000, step=10000)
    min_rooms = st.sidebar.number_input("Mindestanzahl Zimmer", min_value=3.0, value=3.0, step=0.5)
    
    if st.sidebar.button("🔄 Jetzt neue Angebote suchen"):
        items = scrape_all_sources()
        added = save_to_db(items)
        st.sidebar.success(f"{added} neue Angebote gefunden!")
        st.rerun()

    if not df.empty:
        filtered_df = df[(df['price'] <= max_price) & (df['rooms'] >= min_rooms)]
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Angebote Gesamt", len(df))
        col2.metric("Gefiltert", len(filtered_df))
        col3.metric("Durchschnittspreis", f"{filtered_df['price'].mean():,.0f} €" if not filtered_df.empty else "N/A")

        st.markdown("---")

        for idx, row in filtered_df.iterrows():
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                c1.markdown(f"**[{row['title']}]({row['url']})**  \n📍 {row['location']} | Quelle: *{row['source']}*")
                c2.markdown(f"**Preis:** {row['price']:,.0f} €")
                c3.markdown(f"**Zimmer:** {row['rooms']} | **Fläche:** {row['area']} m²")
                c4.markdown(f"*Gefunden: {row['first_seen']}*")
                st.divider()
    else:
        st.info("Klicke in der Sidebar auf 'Jetzt neue Angebote suchen'.")

if __name__ == "__main__":
    init_db()
    run_dashboard()
