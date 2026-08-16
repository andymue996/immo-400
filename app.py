import sqlite3
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st
import datetime

# --- CONFIGURATION & DATABASE SETUP ---
DB_NAME = "kempten_immobilien.db"

PLZ_TARGETS = [
    "87435", "87437", "87439", # Kempten
    "87474", "87448", "87487", "87490", "87493", "87496", "87477", "87497", "87452", # Direktes Umland
    "87459", "87509", "87547", "87527", "87549", "87647", "87657", "87616"  # Erweiterter Radius
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

# --- EXAMPLE SCRAPER MODULE (Regionale Quelle / Beispiel) ---
def scrape_regional_source():
    """
    Beispiel-Funktion zur Demonstration der Datenverarbeitung.
    In der Praxis werden hier die Zielseiten (BSG Allgäu, Regionalmedien, Makler) geparst.
    """
    found_items = []
    
    # Beispielhafter Eintrag (Datenstruktur):
    # In der Produktion sendet requests.get() Anfragen an die Zielseiten
    sample_item = {
        "id": "bsg_10294",
        "title": "Helle 3.5-Zimmer-Wohnung in Waltenhofen",
        "price": 385000.0,
        "rooms": 3.5,
        "area": 84.0,
        "location": "87448 Waltenhofen",
        "url": "https://example.com/immo/10294",
        "source": "BSG Allgäu / Regional"
    }
    found_items.append(sample_item)
    return found_items

def save_to_db(items):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    today = datetime.date.today().isoformat()
    
    new_count = 0
    for item in items:
        # Prüfen, ob der Ort/PLZ zu unseren Ziel-PLZ passt
        if any(plz in item['location'] for plz in PLZ_TARGETS) or "Kempten" in item['location']:
            try:
                c.execute('''
                    INSERT INTO immobilien (id, title, price, rooms, area, location, url, source, first_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (item['id'], item['title'], item['price'], item['rooms'], item['area'], item['location'], item['url'], item['source'], today))
                new_count += 1
            except sqlite3.IntegrityError:
                pass # Bereits in der Datenbank enthalten
    conn.commit()
    conn.close()
    return new_count

# --- STREAMLIT DASHBOARD INTERFACE ---
def run_dashboard():
    st.set_page_config(page_title="Immo-Aggregator Kempten +20km", layout="wide")
    st.title("🏡 Immo-Aggregator Kempten & Umland (+20 km)")
    st.caption("Fokus: Kaufangebote ab 3 Zimmer | Gesamtpreis inkl. Nebenkosten max. 450.000 €")

    # DB verbinden
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM immobilien", conn)
    conn.close()

    # Sidebar Filter
    st.sidebar.header("Filter")
    max_price = st.sidebar.slider("Max. Kaufpreis (€)", 100000, 410000, 410000, step=10000)
    min_rooms = st.sidebar.number_input("Mindestanzahl Zimmer", min_value=3.0, value=3.0, step=0.5)
    
    # Refresh Button
    if st.sidebar.button("🔄 Jetzt neue Angebote suchen"):
        items = scrape_regional_source()
        added = save_to_db(items)
        st.sidebar.success(f"{added} neue Angebote gefunden!")
        st.rerun()

    # Daten filtern
    if not df.empty:
        filtered_df = df[(df['price'] <= max_price) & (df['rooms'] >= min_rooms)]
        
        # Übersichtskennzahlen
        col1, col2, col3 = st.columns(3)
        col1.metric("Angebote Gesamt", len(df))
        col2.metric("Gefiltert", len(filtered_df))
        col3.metric("Durchschnittspreis", f"{filtered_df['price'].mean():,.0f} €" if not filtered_df.empty else "N/A")

        st.markdown("---")

        # Tabellenanzeige
        for idx, row in filtered_df.iterrows():
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                c1.markdown(f"**[{row['title']}]({row['url']})**  \n📍 {row['location']} | Quelle: *{row['source']}*")
                c2.markdown(f"**Preis:** {row['price']:,.0f} €")
                c3.markdown(f"**Zimmer:** {row['rooms']} | **Fläche:** {row['area']} m²")
                c4.markdown(f"*Gefunden: {row['first_seen']}*")
                st.divider()
    else:
        st.info("Noch keine Angebote in der Datenbank. Klicke in der Sidebar auf 'Jetzt neue Angebote suchen'.")

if __name__ == "__main__":
    init_db()
    run_dashboard()
