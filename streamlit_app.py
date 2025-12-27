import streamlit as st
import asyncio
import re
from playwright.async_api import async_playwright
import pandas as pd
from datetime import datetime, timedelta
import playwright_stealth
import csv
import io

# --- CONFIGURAÇÕES DA PÁGINA ---
st.set_page_config(page_title="Automação de Viagens", layout="wide")

# --- FUNÇÕES AUXILIARES (SEU CÓDIGO ORIGINAL) ---
def clean_text_for_csv(text):
    if not text: return ""
    cleaned = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    return re.sub(r'\s+', ' ', cleaned).strip()

def extract_price_usd(text):
    if not text: return None
    match = re.search(r"[$\s]*(?P<price>[\d,]+(?:\.\d{1,2})?)", text.replace('USD', ''), re.IGNORECASE)
    if match:
        return float(match.group('price').replace(",", ""))
    return None

def extract_area_m2(text):
    match = re.search(r"(\d+)\s*(?:m²|sq m|sq metre|sq meter)", text, re.IGNORECASE)
    return int(match.group(1)) if match else None

def generate_overnights(stays):
    overnights = []
    for stay in stays:
        start_date = stay["start"]
        end_date = stay["end"]
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

# --- LÓGICA DE SCRAPING (ADAPTADA) ---
async def scrape_detailed_data(page, hotel_name, hotel_url, checkin, checkout):
    url = f"{hotel_url}?checkin={checkin}&checkout={checkout}&group_adults=2&no_rooms=1&selected_currency=USD&lang=en-us"
    
    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        # Pequena espera para carregar preços dinâmicos
        await page.wait_for_timeout(2000)
        
        # Tenta fechar popups
        try:
            await page.click("button[aria-label*='Close'], .modal-mask-close", timeout=2000)
        except: pass

        rows = await page.query_selector_all("table.hprt-table tbody tr.hprt-table-row")
        extracted_data = []
        last_room_info = {"name": "Desconhecido", "area": None}

        for row in rows:
            room_name_el = await row.query_selector(".hprt-roomtype-link")
            if room_name_el:
                last_room_info["name"] = clean_text_for_csv(await room_name_el.inner_text())
                last_room_info["area"] = extract_area_m2(await row.inner_text())

            price_el = await row.query_selector(".bui-price-display__value, .prco-valign-middle-helper")
            if price_el:
                price_usd = extract_price_usd(await price_el.inner_text())
                if price_usd:
                    extracted_data.append({
                        "Hotel": hotel_name,
                        "Checkin": checkin,
                        "Checkout": checkout,
                        "Quarto": last_room_info["name"],
                        "m2": last_room_info["area"],
                        "Preço (USD)": price_usd
                    })
        return extracted_data
    except Exception as e:
        return []

async def run_automation(stays):
    all_overnights = generate_overnights(stays)
    results = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0...")
        page = await context.new_page()
        await playwright_stealth.stealth(page)

        for i, hotel in enumerate(all_overnights):
            status_text.text(f"Pesquisando {hotel['name']} ({hotel['checkin']})...")
            data = await scrape_detailed_data(page, hotel["name"], hotel["url"], hotel["checkin"], hotel["checkout"])
            results.extend(data)
            progress_bar.progress((i + 1) / len(all_overnights))

        await browser.close()
    return results

# --- INTERFACE STREAMLIT ---
st.title("🏨 Automação de Pesquisa Booking")
st.markdown("Adicione os hotéis e o período para automatizar a coleta de preços por pernoite.")

# Gerenciamento de estado para a lista de hotéis
if 'hotel_list' not in st.session_state:
    st.session_state.hotel_list = []

with st.sidebar:
    st.header("Adicionar Novo Hotel")
    new_name = st.text_input("Nome do Hotel")
    new_url = st.text_input("URL do Booking")
    col_d1, col_d2 = st.columns(2)
    new_start = col_d1.date_input("Início", datetime.now())
    new_end = col_d2.date_input("Fim", datetime.now() + timedelta(days=3))
    
    if st.button("➕ Adicionar à Lista"):
        if new_name and "booking.com" in new_url:
            st.session_state.hotel_list.append({
                "name": new_name, "url": new_url, "start": new_start, "end": new_end
            })
        else:
            st.error("Preencha o nome e uma URL válida do Booking.")

# Exibição da Lista Atual
if st.session_state.hotel_list:
    st.subheader("Hotéis na Fila")
    df_queue = pd.DataFrame(st.session_state.hotel_list)
    st.table(df_queue[['name', 'start', 'end']])
    
    if st.button("🚀 INICIAR COLETA AGORA"):
        with st.spinner("O robô está trabalhando... não feche esta aba."):
            # Executa o loop assíncrono
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            final_data = loop.run_until_complete(run_automation(st.session_state.hotel_list))
            
            if final_data:
                df_final = pd.DataFrame(final_data)
                st.success("Busca Finalizada!")
                st.dataframe(df_final)
                
                # Botão de Download
                csv_data = df_final.to_csv(index=False, sep=";", encoding="utf-8-sig")
                st.download_button("📥 Baixar CSV Resultados", csv_data, "resultados_booking.csv", "text/csv")
            else:
                st.warning("Nenhum dado encontrado. Verifique as URLs ou a disponibilidade.")

    if st.button("🗑️ Limpar Lista"):
        st.session_state.hotel_list = []
        st.rerun()
else:
    st.info("Adicione um hotel na barra lateral para começar.")
