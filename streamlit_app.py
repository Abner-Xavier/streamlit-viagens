import streamlit as st
import asyncio
import re
import os
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import playwright_stealth
import csv

# --- CONFIGURAÇÃO DE AMBIENTE ---
def install_browsers():
    if not os.path.exists("/home/runner/.cache/ms-playwright"):
        with st.spinner("Configurando Agente no servidor..."):
            os.system("playwright install chromium")

# --- FUNÇÕES DE LIMPEZA (SUA LÓGICA PYCHARM) ---
def clean_text(text):
    if not text: return ""
    return re.sub(r'\s+', ' ', text.replace('\n', ' ')).strip()

def extract_usd(text):
    if not text: return None
    match = re.search(r"([\d,.]+)", text.replace('USD', ''))
    if match:
        try: return float(match.group(1).replace(",", ""))
        except: return None
    return None

def extract_m2(text):
    match = re.search(r"(\d+)\s*(?:m²|sq m)", text, re.IGNORECASE)
    return int(match.group(1)) if match else None

# --- AGENTE DE EXTRAÇÃO ---
async def agent_scrape(url_base, checkin, checkout):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        
        # Correção do Stealth para evitar erro de Import
        try:
            await playwright_stealth.stealth_async(page)
        except AttributeError:
            await playwright_stealth.stealth(page)

        url = f"{url_base}?checkin={checkin}&checkout={checkout}&group_adults=2&no_rooms=1&selected_currency=USD&lang=en-us"
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            # Fecha pop-up Genius se aparecer
            try:
                await page.click("button[aria-label*='Close'], button:has-text('Dismiss')", timeout=5000)
            except: pass

            await page.wait_for_selector(".hprt-roomtype-link", timeout=20000)
            rows = await page.query_selector_all("table.hprt-table tbody tr.hprt-table-row")
            
            extracted = []
            last_room = "Desconhecido"
            last_area = None

            for row in rows:
                room_el = await row.query_selector(".hprt-roomtype-link")
                if room_el:
                    last_room = clean_text(await room_el.inner_text())
                    last_area = extract_m2(await row.inner_text())

                price_el = await row.query_selector(".bui-price-display__value, .prco-valign-middle-helper")
                price = extract_usd(await price_el.inner_text()) if price_el else None

                if price:
                    extracted.append({
                        "Suíte": last_room,
                        "Área_m2": last_area,
                        "Preço_USD": price,
                        "Checkin": checkin
                    })
            
            await browser.close()
            return extracted
        except Exception as e:
            await browser.close()
            return []

# --- INTERFACE (FRONT-END) ---
st.set_page_config(page_title="Agente de Suítes", layout="wide")
st.title("🏨 Agente de Inventário de Suítes")
st.subheader("Otimização de tempo para equipe de análise")

with st.sidebar:
    st.header("Configuração")
    url_input = st.text_input("URL do Booking")
    d_in = st.date_input("Check-in", datetime.now() + timedelta(days=7))
    d_out = st.date_input("Check-out", d_in + timedelta(days=1))
    
    # Gerador de Pernoites
    if st.button("Adicionar Período"):
        st.session_state.target = {"url": url_input, "in": str(d_in), "out": str(d_out)}

if 'target' in st.session_state:
    st.write(f"🎯 **Destino:** {st.session_state.target['url']}")
    
    if st.button("🚀 INICIAR AGENTE"):
        install_browsers()
        status = st.empty()
        
        # Rodar o robô
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with st.spinner("O agente está mapeando o inventário..."):
            res = loop.run_until_complete(agent_scrape(
                st.session_state.target['url'], 
                st.session_state.target['in'], 
                st.session_state.target['out']
            ))
        
        if res:
            df = pd.DataFrame(res)
            
            # --- RESUMO PARA ECONOMIZAR 45 MINUTOS ---
            st.success("Mapeamento concluído!")
            
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("### 📊 Suite Count & m²")
                resumo = df.groupby(['Suíte', 'Área_m2']).size().reset_index(name='Quantidade')
                st.table(resumo)
            
            with col_b:
                st.write("### 💵 Médias de Preço")
                media = df.groupby('Suíte')['Preço_USD'].mean().reset_index()
                st.dataframe(media)

            st.write("### 📋 Tabela Completa")
            st.dataframe(df)
            
            # Exportação
            csv_data = df.to_csv(index=False, sep=";").encode('utf-8-sig')
            st.download_button("📥 Baixar Planilha para Relatório", csv_data, "inventario.csv", "text/csv")
        else:
            st.error("Falha na extração. O site pode ter bloqueado ou não há vagas.")
