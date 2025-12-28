import streamlit as st
import asyncio
import re
import os
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
import csv

# --- CONFIGURAÇÃO DE AMBIENTE CLOUD ---
def install_playwright():
    if not os.path.exists("/home/adminuser/.cache/ms-playwright"):
        st.info("Configurando navegadores pela primeira vez...")
        os.system("playwright install chromium")

# --- FUNÇÕES AUXILIARES (Baseadas no seu Pycharm) ---
def generate_overnights(stays):
    overnights = []
    for stay in stays:
        start_date = datetime.strptime(stay["start"], "%Y-%m-%d")
        end_date = datetime.strptime(stay["end"], "%Y-%m-%d")
        current_checkin = start_date
        while current_checkin < end_date:
            current_checkout = current_checkin + timedelta(days=1)
            overnights.append({
                "name": stay["name"],
                "url": stay["url"],
                "checkin": current_checkin.strftime("%Y-%m-%d"),
                "checkout": current_checkout.strftime("%Y-%m-%d"),
            })
            current_checkin = current_checkout
    return overnights

def extract_price_usd(text):
    if not text: return None
    match = re.search(r"[$\s]*(?P<price>[\d,]+(?:\.\d{1,2})?)", text.replace('USD', ''), re.IGNORECASE)
    if match:
        try: return float(match.group('price').replace(",", ""))
        except: return None
    return None

# --- SCRAPER PRINCIPAL ---
async def scrape_detailed_data(page, hotel_name, hotel_url, checkin, checkout):
    url = f"{hotel_url}?checkin={checkin}&checkout={checkout}&group_adults=2&no_rooms=1&selected_currency=USD&lang=en-us"
    
    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        
        # Fecha pop-ups e Genius (Crítico para evitar o erro do seu print)
        try:
            await page.click("button:has-text('Dismiss'), button[aria-label*='Close dialog']", timeout=5000)
        except: pass

        await page.wait_for_selector(".hprt-roomtype-link", timeout=15000)
        
        rows = await page.query_selector_all("table.hprt-table tbody tr.hprt-table-row")
        extracted_data = []
        last_room_name = "Desconhecido"

        for row in rows:
            room_el = await row.query_selector(".hprt-roomtype-link")
            if room_el:
                last_room_name = (await room_el.inner_text()).strip()

            price_el = await row.query_selector(".bui-price-display__value, .prco-valign-middle-helper")
            price = extract_price_usd(await price_el.inner_text()) if price_el else None

            if price:
                extracted_data.append({
                    "Hotel": hotel_name,
                    "Checkin": checkin,
                    "Room": last_room_name,
                    "Price_USD": price
                })
        return extracted_data
    except Exception as e:
        return []

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="Booking Scraper PRO", layout="wide")
st.title("🏨 Booking Data Extractor")

# Inicializa lista de hotéis
if 'hoteis' not in st.session_state:
    st.session_state.hoteis = [
        {"name": "Grand Hyatt Istanbul", "url": "https://www.booking.com/hotel/tr/grand-hyatt-istanbul.html", "start": "2025-12-27", "end": "2025-12-29"}
    ]

# Sidebar para adicionar novos hotéis
with st.sidebar:
    st.header("Adicionar Hotel")
    new_name = st.text_input("Nome")
    new_url = st.text_input("URL do Booking")
    d_start = st.date_input("Início")
    d_end = st.date_input("Fim")
    if st.button("Adicionar à Lista"):
        st.session_state.hoteis.append({"name": new_name, "url": new_url, "start": str(d_start), "end": str(d_end)})

st.write("### Lista de Monitoramento", pd.DataFrame(st.session_state.hoteis))

if st.button("🚀 INICIAR COLETA COMPLETA"):
    install_playwright()
    all_overnights = generate_overnights(st.session_state.hoteis)
    final_results = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()

    async def run_task():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(user_agent="Mozilla/5.0...", viewport={"width": 1280, "height": 800})
            page = await context.new_page()
            await stealth_async(page)

            for i, hotel in enumerate(all_overnights):
                status_text.text(f"Processando {i+1}/{len(all_overnights)}: {hotel['name']}")
                data = await scrape_detailed_data(page, hotel["name"], hotel["url"], hotel["checkin"], hotel["checkout"])
                final_results.extend(data)
                progress_bar.progress((i + 1) / len(all_overnights))
            
            await browser.close()

    asyncio.run(run_task())

    if final_results:
        df = pd.DataFrame(final_results)
        st.success("Busca finalizada!")
        st.dataframe(df)
        
        # Botão de Download CSV
        csv_data = df.to_csv(index=False, sep=";", encoding="utf-8-sig")
        st.download_button("📥 Baixar Planilha CSV", csv_data, "hoteis_booking.csv", "text/csv")
    else:
        st.error("Nenhum dado encontrado. Verifique se o Booking bloqueou o acesso ou se as datas são válidas.")
