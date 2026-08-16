 
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

# --- 1. SCRAPER OHNE-MAKLER ---
def scrape_ohne_makler():
    items = []
    url = "https://www.ohne-makler.net/immobilien/wohnung-kaufen/bayern/kempten-allgau/"
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            seen_ids = set()
            for a in soup.select('a[href*="/immobilie/"]'):
                href = a.get("href", "")
                m = re.search(r'/immobilie/(\d+)/', href)
                if not m:
                    continue
                listing_id = m.group(1)
                if listing_id in seen_ids:
                    continue  
                text = a.get_text(" ", strip=True)
                if "€" not in text:
                    continue

                link = href if href.startswith("http") else "https://www.ohne-makler.net" + href

                price = extract_number(text, r'([\d\.]{4,})\s*€', default=350000.0)
                area = extract_number(text, r'([\d,\.]+)\s*m²', default=80.0)
                rooms = extract_number(text, r'(\d+)\s+[\d,\.]+\s*m²', default=3.0)

                seen_ids.add(listing_id)
                title = text.split("€")[0].strip()

                items.append({
                    "id": f"om_{listing_id}",
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

# --- 1b. SCRAPER HOLD IMMOBILIEN ---
def scrape_hold_immobilien():
    items = []
    url = "https://hold-immobilien.de/immobilien-kaufen"
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            seen = set()
            for a in soup.select('a[href*="/immobilien-kaufen/"]'):
                href = a.get("href", "")
                if href.rstrip("/").endswith("/immobilien-kaufen"):
                    continue  
                if href in seen:
                    continue

                scope = a
                card_text = ""
                for _ in range(6):
                    if scope.parent is None:
                        break
                    scope = scope.parent
                    card_text = scope.get_text(" ", strip=True)
                    if "Zimmer" in card_text and ("Kaufpreis" in card_text or "EUR" in card_text):
                        break

                if "Zimmer" not in card_text:
                    continue

                seen.add(href)
                link = href if href.startswith("http") else "https://hold-immobilien.de" + href

                price = extract_number(card_text, r'Kaufpreis:\s*([\d\.]+)\s*EUR', default=0.0)
                rooms = extract_number(card_text, r'Zimmer:\s*([\d,\.]+)', default=3.0)
                area = extract_number(card_text, r'Wohnfläche ca\.:\s*([\d,\.]+)\s*m', default=80.0)
                title = (a.get_text(strip=True) or "Hold Immobilien Angebot")[:80]

                items.append({
                    "id": f"hold_{abs(hash(href))}",
                    "title": title,
                    "price": price if price > 0 else 0.0,  
                    "rooms": rooms,
                    "area": area,
                    "location": "Allgäu",
                    "url": link,
                    "source": "Hold Immobilien"
                })
    except Exception as e:
        print(f"Hinweis Scraper: {e}")
    return items

# --- 2. UMFANGREICHE DIREKTLINKS (OHNE BSG, HERZSTUBEN & SOZIALBAU) ---
def fetch_regional_allgaeu_feed():
    return [
        {
            "id": "kleinanzeigen_kempten_20km",
            "title": "Kleinanzeigen: Kaufwohnungen Kempten + 20km Umkreis",
            "price": 320000.0,
            "rooms": 3.0,
            "area": 80.0,
            "location": "Kempten & 20km Umkreis",
            "url": "https://www.kleinanzeigen.de/s-wohnung-kaufen/kempten/c196l7586r20",
            "source": "Kleinanzeigen (Privat & Makler)"
        },
        {
            "id": "immowelt_kempten_all",
            "title": "Immowelt: Alle Eigentumswohnungen in Kempten (Allgäu)",
            "price": 350000.0,
            "rooms": 3.0,
            "area": 85.0,
            "location": "87435 Kempten",
            "url": "https://www.immowelt.de/liste/kempten-allgau/wohnungen/kaufen",
            "source": "Immowelt"
        },
        {
            "id": "immoscout_kempten_3zi",
            "title": "ImmoScout24: Wohnungen kaufen in Kempten",
            "price": 380000.0,
            "rooms": 3.0,
            "area": 88.0,
            "location": "87439 Kempten",
            "url": "https://www.immobilienscout24.de/Suche/de/bayern/kempten-allgaeu/wohnung-kaufen",
            "source": "ImmoScout24"
        },
        {
            "id": "spk_allgaeu_suche",
            "title": "Sparkasse Allgäu: Immobilien-Kaufangebote Kempten",
            "price": 339000.0,
            "rooms": 3.0,
            "area": 82.0,
            "location": "87435 Kempten",
            "url": "https://immobilien.sparkasse.de/immobilien/bayern/kempten.html",
            "source": "Sparkasse Allgäu"
        },
        {
            "id": "vr_bank_ke_oa",
            "title": "VR Bank Kempten-Oberallgäu: Immobilien-Börse",
            "price": 325000.0,
            "rooms": 3.0,
            "area": 76.0,
            "location": "Kempten / Oberallgäu",
            "url": "https://www.vrbank-ke-oa.de/privatkunden/immobilie-und-wohnen/produkte/immobilien/immobiliensuche.html",
            "source": "VR Bank Kempten-Oberallgäu"
        },
        {
            "id": "brimo_immo_ke",
            "title": "BRIMO Allgäu Immobilien: Wohnungsangebote",
            "price": 335000.0,
            "rooms": 3.0,
            "area": 85.0,
            "location": "Kempten",
            "url": "https://allgaeu-immobilie.de/",
            "source": "BRIMO Allgäu"
        }
    ]

def scrape_all_sources():
    all_found = []
    all_found.extend(scrape_ohne_makler())
    all_found.extend(scrape_hold_immobilien())
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
            c.execute('''
                UPDATE immobilien 
                SET title=?, price=?, rooms=?, area=?, location=?, url=?, source=?
                WHERE id=?
            ''', (item['title'], item['price'], item['rooms'], item['area'], item['location'], item['url'], item['source'], item['id']))
    conn.commit()
    conn.close()
    return new_count

def run_dashboard():
    st.set_page_config(page_title="Immo-Aggregator Kempten +20km", layout="wide")
    st.title("🏡 Immo-Aggregator Kempten & Umland (+20 km)")
    st.caption("Echtzeit-Verlinkungen zu Kleinanzeigen, ImmoScout24, Immowelt, Sparkasse, VR Bank & regionalen Maklern")

    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT * FROM immobilien", conn)
    conn.close()

    st.sidebar.header("Filter & Steuerung")
    
    if st.sidebar.button("🗑️ Datenbank komplett zurücksetzen"):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DELETE FROM immobilien")
        conn.commit()
        conn.close()
        st.sidebar.warning("Datenbank geleert!")
        st.rerun()

    max_price = st.sidebar.slider("Max. Kaufpreis (€)", 100000, 600000, 500000, step=10000)
    min_rooms = st.sidebar.number_input("Mindestanzahl Zimmer", min_value=1.0, value=1.0, step=0.5)
    
    if st.sidebar.button("🔄 Alle Quellen neu laden"):
        with st.spinner("Sammle alle aktuellen Links und Angebote..."):
            items = scrape_all_sources()
            save_to_db(items)
            st.sidebar.success("Erfolgreich aktualisiert!")
            st.rerun()

    if not df.empty:
        filtered_df = df[(df['price'] <= max_price) & (df['rooms'] >= min_rooms)]
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Quellen im System", len(df))
        col2.metric("Nach Filter angezeigt", len(filtered_df))
        col3.metric("Ø-Richtpreis", f"{filtered_df['price'].mean():,.0f} €" if not filtered_df.empty else "N/A")

        st.markdown("---")

        for idx, row in filtered_df.iterrows():
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                c1.markdown(f"**[{row['title']}]({row['url']})**  \n📍 {row['location']} | Quelle: **{row['source']}**")
                c2.markdown(f"**Preis ca.:** {row['price']:,.0f} €")
                c3.markdown(f"**Zimmer:** {row['rooms']} | **Fläche:** {row['area']} m²")
                c4.markdown(f"[🔗 Portal öffnen]({row['url']})")
                st.divider()
    else:
        st.info("Klicke in der Sidebar auf 'Alle Quellen neu laden'.")

if __name__ == "__main__":
    init_db()
    run_dashboard()







