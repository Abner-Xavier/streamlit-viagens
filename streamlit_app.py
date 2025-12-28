import streamlit as st
import asyncio
import re
import os
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
import csv

# --- CONFIGURAÇÃO DE AMBIENTE ---
def install_playwright():
    if not os.path.exists("/home/adminuser/.cache/ms-playwright"):
        os.system("playwright install chromium")

# --- LÓGICA DE DATAS (PYCHARM) ---
def generate_overnights(stays):
    overnights = []
    for stay in stays:
        start_date = datetime.strptime(stay["start"], "%Y-%m-%d")
        end_date = datetime.strptime(stay["end"], "%Y-%m-%d")
        curr = start_date
        while curr < end_date:
            nxt = curr + timedelta(days=1)
            overnights.append({
                "name": stay["name"], "url": stay["url"],
                "checkin": curr.strftime("%Y-%m-%d"), "checkout": nxt.strftime("%Y-%m-%d")
            })
            curr = nxt
    return overnights

# --- SCRAPER DETALHADO (PYCHARM ADAPTADO) ---
async def scrape_booking_detailed(page, hotel):
    url = f"{hotel['url']}?checkin={hotel['checkin']}&checkout={hotel['checkout']}&group_adults=2&no_rooms=1&selected_currency=USD&lang=en-us"
    
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Fecha pop-ups (Genius/Cookies) que bloqueiam a tela
        try:
            await page.click("button:has-text('Dismiss'), button[aria-label*='Close dialog']", timeout=5000)
        except: pass

        # Espera a tabela de quartos carregar (Seletor do seu PyCharm)
        await page.wait_for_selector(".hprt-roomtype-link", timeout=20000)
        
        rows = await page.query_selector_all("table.hprt-table tbody tr.hprt-table-row")
        data = []
        last_room = "Desconhecido"

        for row in rows:
            room_el = await row.query_selector(".hprt-roomtype-link")
            if room_el:
                last_room = (await room_el.inner_text()).strip()

            price_el = await row.query_selector(".bui-price-display__value, .prco-valign-middle-helper")
            if price_el:
                price_text = await price_el.inner_text()
                # Limpeza de preço simplificada
                price_match = re.search(r"([\d,.]+)", price_text.replace("USD", ""))
                price_val = float(price_match.group(1).replace(",", "")) if price_match else None
                
                if price_val:
                    data.append({
                        "Hotel": hotel['name'], "Check-in": hotel['checkin'],
                        "Quarto": last_room, "Preço_USD": price_val
                    })
        return data
    except Exception:
        return []

# --- INTERFACE STREAMLIT ---
st.title("🏨 Booking Detailed Scraper")

if 'fila' not in st.session_state:
    st.session_state.fila = []

with st.sidebar:
    st.header("Configurar Estadias")
    name = st.text_input("Nome do Hotel")
    url = st.text_input("URL do Hotel")
    d1 = st.date_input("Início", datetime.now() + timedelta(days=10))
    d2 = st.date_input("Fim", d1 + timedelta(days=3))
    if st.button("Adicionar"):
        st.session_state.fila.append({"name": name, "url": url, "start": str(d1), "end": str(d2)})

if st.session_state.fila:
    st.write("Fila de Processamento:", pd.DataFrame(st.session_state.fila))
    
    if st.button("🚀 EXECUTAR SCRAPER"):
        install_playwright()
        overnights = generate_overnights(st.session_state.fila)
        all_data = []
        
        progress = st.progress(0)
        status = st.empty()

        async def main():
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
                context = await browser.new_context(user_agent="Mozilla/5.0...")
                page = await context.new_page()
                await stealth_async(page)

                for i, h in enumerate(overnights):
                    status.info(f"Processando: {h['name']} ({h['checkin']})")
                    res = await scrape_booking_detailed(page, h)
                    all_data.extend(res)
                    progress.progress((i + 1) / len(overnights))
                
                await browser.close()

        asyncio.run(main())

        if all_data:
            df = pd.DataFrame(all_data)
            st.success("Coleta finalizada!")
            st.dataframe(df)
            st.download_button("📥 Baixar CSV", df.to_csv(index=False, sep=";").encode('utf-8-sig'), "booking_results.csv")
        else:
            st.error("Nenhum dado extraído. O site pode ter bloqueado o acesso.")
