import streamlit as st
import asyncio
import re
import os
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from playwright_stealth import stealth

# --- CONFIGURAÇÃO INICIAL ---
def setup_playwright():
    if not os.path.exists("/home/runner/.cache/ms-playwright"):
        os.system("playwright install chromium")

# --- LÓGICA DE EXTRAÇÃO (BACK-END) ---
async def extrair_suites_agente(url_base, checkin, checkout):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        await stealth(page)

        # Monta a URL (Baseada na sua lógica de pernoite)
        url = f"{url_base}?checkin={checkin}&checkout={checkout}&selected_currency=USD&lang=en-us"
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Fecha pop-ups que atrapalham a equipe
            try:
                await page.click("button[aria-label*='Close'], button:has-text('Dismiss')", timeout=5000)
            except: pass

            await page.wait_for_selector(".hprt-roomtype-link", timeout=20000)
            
            rows = await page.query_selector_all("table.hprt-table tbody tr.hprt-table-row")
            dados_brutos = []
            current_room = "Desconhecido"
            current_area = 0

            for row in rows:
                # Extrai Nome e Area (m2)
                room_el = await row.query_selector(".hprt-roomtype-link")
                if room_el:
                    current_room = (await room_el.inner_text()).strip()
                    full_text = await row.inner_text()
                    match_area = re.search(r"(\d+)\s*(?:m²|sq m)", full_text)
                    current_area = int(match_area.group(1)) if match_area else 0

                # Extrai Preço
                price_el = await row.query_selector(".bui-price-display__value")
                if price_el:
                    price_text = await price_el.inner_text()
                    price_match = re.search(r"([\d,.]+)", price_text.replace("USD", ""))
                    price_val = float(price_match.group(1).replace(",", "")) if price_match else 0
                    
                    dados_brutos.append({
                        "Tipo de Suite": current_room,
                        "m2": current_area,
                        "Preço USD": price_val
                    })

            await browser.close()
            return dados_brutos
        except Exception as e:
            await browser.close()
            return []

# --- INTERFACE PARA A EQUIPE (FRONT-END) ---


st.set_page_config(page_title="Agente de Inventário", layout="wide")
st.title("🤖 Agente de Inventário de Suítes")
st.info("Este agente automatiza a extração que leva 45 minutos. Insira os dados abaixo:")

with st.container():
    url_hotel = st.text_input("Cole aqui a URL do Hotel no Booking:")
    c1, c2 = st.columns(2)
    with c1:
        checkin = st.date_input("Check-in", datetime.now() + timedelta(days=7))
    with c2:
        checkout = st.date_input("Check-out", checkin + timedelta(days=1))

if st.button("🚀 Iniciar Mapeamento"):
    if not url_hotel:
        st.warning("Por favor, insira a URL.")
    else:
        setup_playwright()
        with st.spinner("O Agente está lendo o site e contando as suítes..."):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            resultados = loop.run_until_complete(extrair_suites_agente(url_hotel, str(checkin), str(checkout)))
            
            if resultados:
                df = pd.DataFrame(resultados)
                
                # --- OTIMIZAÇÃO PARA A EQUIPE (SUITE COUNT) ---
                st.subheader("📊 Resumo de Inventário (Suite Count)")
                resumo = df.groupby(['Tipo de Suite', 'm2']).agg({
                    'Preço USD': 'mean',
                    'Tipo de Suite': 'count'
                }).rename(columns={'Tipo de Suite': 'Qtd Ofertas'}).reset_index()
                
                st.table(resumo)
                
                st.subheader("📋 Lista Detalhada")
                st.dataframe(df)
                
                csv = df.to_csv(index=False, sep=";").encode('utf-8-sig')
                st.download_button("📥 Baixar Planilha para Relatório", csv, "inventario_hotel.csv", "text/csv")
            else:
                st.error("O agente não encontrou quartos. Verifique a URL ou se há disponibilidade nas datas.")

st.sidebar.markdown("---")
st.sidebar.write("💡 **Dica:** Enquanto o agente roda, você pode trabalhar em outras abas. Ele notificará quando terminar.")
