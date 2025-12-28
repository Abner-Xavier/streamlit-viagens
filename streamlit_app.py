import streamlit as st
import asyncio
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import os

def install_playwright_browsers():
    if not os.path.exists("/home/adminuser/.cache/ms-playwright"):
        os.system("playwright install chromium")

async def coletar_dados(page, hotel_nome, checkin, checkout):
    resultados = []
    query = hotel_nome.replace(" ", "+")
    url = f"https://www.booking.com/searchresults.pt-br.html?ss={query}&checkin={checkin}&checkout={checkout}&selected_currency=USD"

    try:
        await page.goto(url, wait_until="load", timeout=60000)
        await asyncio.sleep(5) 

        # --- LÓGICA PARA FECHAR O POP-UP DO GENIUS (Visto no seu print) ---
        try:
            # Tenta clicar no botão de fechar (X) ou fora do modal
            popup_close = page.locator('button[aria-label="Ignorar informações de login"]')
            if await popup_close.is_visible():
                await popup_close.click()
                st.info("Pop-up Genius fechado.")
        except:
            pass

        # Localizar o hotel
        card = await page.wait_for_selector('[data-testid="property-card"]', timeout=20000)
        
        if card:
            nome = await card.locator('[data-testid="title"]').inner_text()
            try:
                preco = await card.locator('[data-testid="price-and-discounted-price"]').inner_text()
            except:
                preco = "Ver no site"

            resultados.append({
                "Hotel": nome,
                "Preço": preco,
                "Check-in": checkin,
                "Check-out": checkout
            })
        
        return resultados

    except Exception as e:
        await page.screenshot(path="erro_debug.png")
        return resultados

async def rodar_scrapers(hoteis):
    install_playwright_browsers()
    dados_finais = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        for hotel in hoteis:
            page = await context.new_page()
            dados = await coletar_dados(page, hotel["nome"], hotel["ini"].strftime("%Y-%m-%d"), hotel["fim"].strftime("%Y-%m-%d"))
            dados_finais.extend(dados)
            await page.close()
            
        await browser.close()
    return dados_finais

# --- INTERFACE ---
st.title("🏨 Buscador Booking")
if "fila" not in st.session_state: st.session_state.fila = []

with st.sidebar:
    nome = st.text_input("Hotel")
    c1, c2 = st.columns(2)
    ini = c1.date_input("Check-in", datetime.now() + timedelta(days=7))
    fim = c2.date_input("Check-out", ini + timedelta(days=3))
    if st.button("Adicionar"):
        st.session_state.fila.append({"nome": nome, "ini": ini, "fim": fim})

if st.session_state.fila:
    st.write(st.session_state.fila)
    if st.button("🚀 INICIAR BUSCA"):
        with st.spinner("Buscando..."):
            res = asyncio.run(rodar_scrapers(st.session_state.fila))
            if res:
                st.dataframe(pd.DataFrame(res))
            else:
                st.error("Erro. Verifique o print de debug abaixo.")
                if os.path.exists("erro_debug.png"):
                    st.image("erro_debug.png")
