import streamlit as st
import asyncio
import re
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import os

# --- GARANTIR QUE O NAVEGADOR ESTEJA INSTALADO ---
def install_playwright_browsers():
    # Verifica se o navegador já existe para não baixar toda vez
    if not os.path.exists("/home/adminuser/.cache/ms-playwright"):
        os.system("playwright install chromium")

# --- FUNÇÃO DE COLETA (SELETORES ATUALIZADOS) ---
async def coletar_dados(page, hotel_nome, checkin, checkout):
    resultados = []
    query = hotel_nome.replace(" ", "+")
    
    # URL com moeda em USD e idioma PT-BR
    url = (
        f"https://www.booking.com/searchresults.pt-br.html"
        f"?ss={query}&checkin={checkin}&checkout={checkout}&selected_currency=USD"
    )

    try:
        # Aumentamos o timeout para 60s devido à lentidão do servidor cloud
        await page.goto(url, wait_until="load", timeout=60000)
        await asyncio.sleep(4) # Pausa para carregar preços dinâmicos

        # Tentar fechar pop-up de login/cookies se aparecer
        try:
            await page.click("button[aria-label='Ignorar informações de login']", timeout=3000)
        except: pass

        # Localizar o primeiro card de hotel
        card = await page.wait_for_selector('[data-testid="property-card"]', timeout=15000)
        
        if card:
            # Pegar informações básicas do primeiro resultado
            nome_encontrado = await card.locator('[data-testid="title"]').inner_text()
            
            # Tentar capturar o preço com seletores alternativos
            try:
                preco_txt = await card.locator('[data-testid="price-and-discounted-price"]').inner_text()
            except:
                preco_txt = "Preço não disponível"

            resultados.append({
                "Hotel Pesquisado": hotel_nome,
                "Hotel Encontrado": nome_encontrado,
                "Check-in": checkin,
                "Check-out": checkout,
                "Preço": preco_txt
            })
        
        return resultados

    except Exception as e:
        # Tira um print se algo der errado (ajuda a ver se houve bloqueio/Captcha)
        await page.screenshot(path="erro_booking.png")
        return resultados

async def rodar_scrapers(hoteis):
    dados_finais = []
    install_playwright_browsers()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )

        progresso = st.progress(0.0)
        status = st.empty()

        for i, hotel in enumerate(hoteis):
            page = await context.new_page()
            
            # Gerar datas de pernoite (lógica que você já tinha)
            d_ini = hotel["ini"]
            d_fim = hotel["fim"]
            
            status.info(f"🔎 Pesquisando: {hotel['nome']}")
            
            # Chamada simplificada para o primeiro período
            dados = await coletar_dados(page, hotel["nome"], d_ini.strftime("%Y-%m-%d"), d_fim.strftime("%Y-%m-%d"))
            dados_finais.extend(dados)

            await page.close()
            progresso.progress((i + 1) / len(hoteis))

        await browser.close()
    return dados_finais

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="Booking Bot", layout="wide")
st.title("🏨 Buscador Booking Corrigido")

if "fila" not in st.session_state:
    st.session_state.fila = []

with st.sidebar:
    st.header("Novo Hotel")
    nome = st.text_input("Nome do Hotel")
    c1, c2 = st.columns(2)
    ini = c1.date_input("Check-in", datetime.now() + timedelta(days=7))
    fim = c2.date_input("Check-out", ini + timedelta(days=2))

    if st.button("Adicionar"):
        st.session_state.fila.append({"nome": nome, "ini": ini, "fim": fim})
        st.rerun()

    if st.button("Limpar Tudo"):
        st.session_state.fila = []
        st.rerun()

if st.session_state.fila:
    st.table(pd.DataFrame(st.session_state.fila))
    if st.button("🚀 INICIAR BUSCA"):
        resultado = asyncio.run(rodar_scrapers(st.session_state.fila))
        
        if resultado:
            df = pd.DataFrame(resultado)
            st.success("Busca Finalizada!")
            st.dataframe(df)
        else:
            st.error("Não foi possível extrair dados. Veja o print abaixo.")
            if os.path.exists("erro_booking.png"):
                st.image("erro_booking.png", caption="O que o robô viu (Possível Bloqueio)")
