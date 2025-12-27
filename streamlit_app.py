import streamlit as st
import asyncio
import os
import re
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import playwright_stealth

# --- 1. BOOTSTRAP: Garante que o Chromium esteja instalado no servidor ---
def install_playwright():
    try:
        import playwright
    except ImportError:
        os.system("pip install playwright")
    # Instala o binário do Chromium se não existir
    os.system("playwright install chromium")

if 'browsers_installed' not in st.session_state:
    with st.spinner("Configurando ambiente do navegador (isso ocorre apenas no primeiro acesso)..."):
        install_playwright()
        st.session_state['browsers_installed'] = True

# --- 2. FUNÇÕES DE APOIO (Lógica da sua Foto 2) ---

def generate_overnights(name, url, start_date, end_date):
    """Gera a lista de pernoites individuais (1 noite por vez)"""
    overnights = []
    curr = start_date
    while curr < end_date:
        nxt = curr + timedelta(days=1)
        overnights.append({
            "name": name,
            "url": url,
            "checkin": curr.strftime("%Y-%m-%d"),
            "checkout": nxt.strftime("%Y-%m-%d")
        })
        curr = nxt
    return overnights

async def scrape_booking(page, hotel):
    url = f"{hotel['url']}?checkin={hotel['checkin']}&checkout={hotel['checkout']}&group_adults=2&no_rooms=1&selected_currency=USD&lang=en-us"
    
    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000) # Espera renderizar preços

        rows = await page.query_selector_all("table.hprt-table tbody tr.hprt-table-row")
        data = []
        last_room = "Desconhecido"
        last_area = None

        for row in rows:
            # Nome do Quarto
            name_el = await row.query_selector(".hprt-roomtype-link")
            if name_el:
                last_room = (await name_el.inner_text()).strip()
                # Extração simples de área (m2)
                row_text = await row.inner_text()
                area_match = re.search(r"(\d+)\s*(?:m²|sq m)", row_text)
                last_area = int(area_match.group(1)) if area_match else None

            # Preço
            price_el = await row.query_selector(".bui-price-display__value, .prco-valign-middle-helper")
            if price_el:
                price_text = await price_el.inner_text()
                price_match = re.search(r"[\d,.]+", price_text.replace("$", ""))
                if price_match:
                    price_val = float(price_match.group().replace(",", ""))
                    
                    data.append({
                        "Hotel_Name": hotel['name'],
                        "Checkin": hotel['checkin'],
                        "Checkout": hotel['checkout'],
                        "Room_Name": last_room,
                        "Area_m2": last_area,
                        "Price_USD": price_val,
                        "Qty_Available": 5 # Valor fixo ou extraído se disponível
                    })
        return data
    except Exception as e:
        return []

# --- 3. INTERFACE STREAMLIT ---

st.set_page_config(page_title="Travel Automation", layout="wide")
st.title("🏨 Automação de Pesquisa Booking")

with st.sidebar:
    st.header("Adicionar Hotel")
    h_name = st.text_input("Nome do Hotel", value="Hyatt Regency Lisbon")
    h_url = st.text_input("URL do Booking")
    d_start = st.date_input("Início", datetime(2025, 12, 27))
    d_end = st.date_input("Fim", datetime(2025, 12, 30))
    
    if st.button("➕ Adicionar à Lista"):
        if 'hotels' not in st.session_state: st.session_state.hotels = []
        st.session_state.hotels.append({"name": h_name, "url": h_url, "start": d_start, "end": d_end})

if 'hotels' in st.session_state and st.session_state.hotels:
    st.write("### Fila de Processamento")
    st.table(pd.DataFrame(st.session_state.hotels))

    if st.button("🚀 INICIAR COLETA AGORA"):
        all_results = []
        progress = st.progress(0)
        status = st.empty()

        async def run_task():
            async with async_playwright() as p:
                # O segredo para não dar erro no Streamlit Cloud: --no-sandbox
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
                context = await browser.new_context(user_agent="Mozilla/5.0...")
                page = await context.new_page()
                await playwright_stealth.stealth(page)

                for hotel_task in st.session_state.hotels:
                    overnights = generate_overnights(hotel_task['name'], hotel_task['url'], hotel_task['start'], hotel_task['end'])
                    
                    for i, night in enumerate(overnights):
                        status.markdown(f"🔎 Coletando: **{night['name']}** | {night['checkin']}")
                        day_data = await scrape_booking(page, night)
                        all_results.extend(day_data)
                
                await browser.close()
            return all_results

        # Execução
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        final_df_data = loop.run_until_complete(run_task())

        if final_df_data:
            df = pd.DataFrame(final_df_data)
            st.success("Coleta Concluída!")
            st.dataframe(df, use_container_width=True) # Exibe igual à Foto 2
            st.download_button("📥 Baixar Planilha (CSV)", df.to_csv(index=False), "pesquisa.csv")
