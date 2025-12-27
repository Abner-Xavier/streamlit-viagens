import os
import streamlit as st
import asyncio
import re
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from playwright_stealth import stealth

# --- 1. INSTALAÇÃO DO NAVEGADOR ---
def install_playwright_stuff():
    if 'playwright_ready' not in st.session_state:
        with st.spinner("Configurando ambiente do Chrome..."):
            os.system("playwright install chromium")
            st.session_state.playwright_ready = True

# --- 2. LÓGICA DE DATAS ---
def gerar_periodos_pernoite(start_date, end_date):
    periodos = []
    atual = start_date
    while atual < end_date:
        proximo = atual + timedelta(days=1)
        periodos.append((atual.strftime("%Y-%m-%d"), proximo.strftime("%Y-%m-%d")))
        atual = proximo
    return periodos

async def coletar_dados_booking(page, hotel_name, url_base, checkin, checkout):
    # Limpa a URL caso ela venha com parâmetros de busca antigos
    url_limpa = url_base.split('?')[0]
    url = f"{url_limpa}?checkin={checkin}&checkout={checkout}&group_adults=2&no_rooms=1&selected_currency=USD&lang=en-us"
    
    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)

        rows = await page.query_selector_all("table.hprt-table tbody tr.hprt-table-row")
        resultados = []
        quarto, area = "Desconhecido", None

        for row in rows:
            nome_el = await row.query_selector(".hprt-roomtype-link")
            if nome_el:
                quarto = (await nome_el.inner_text()).strip()
                texto = await row.inner_text()
                area_match = re.search(r"(\d+)\s*(?:m²|sq m)", texto)
                area = int(area_match.group(1)) if area_match else None

            preco_el = await row.query_selector("span[data-testid='price-and-discounted-price'], .bui-price-display__value, .prco-valign-middle-helper")
            if preco_el:
                preco_raw = await preco_el.inner_text()
                preco_num = re.search(r"[\d,.]+", preco_raw)
                if preco_num:
                    resultados.append({
                        "Hotel_Name": hotel_name,
                        "Checkin": checkin,
                        "Checkout": checkout,
                        "Room_Name": quarto,
                        "Area_m2": area,
                        "Price_USD": float(preco_num.group().replace(",", "")),
                        "Qty_Available": 5
                    })
        return resultados
    except:
        return []

# --- 3. INTERFACE ---
st.set_page_config(page_title="Viagens Automation", layout="wide")
st.title("🏨 Automação de Pesquisa Booking")

# INICIALIZA A LISTA VAZIA (Remove os hotéis padrão)
if "hoteis_lista" not in st.session_state:
    st.session_state.hoteis_lista = []

with st.sidebar:
    st.header("Configurações")
    # Deixamos os campos vazios para você preencher
    h_nome = st.text_input("Nome do Hotel", placeholder="Ex: Hyatt Regency Lisbon")
    h_url = st.text_input("URL do Booking", placeholder="Cole o link do hotel aqui")
    
    col1, col2 = st.columns(2)
    with col1:
        d_ini = st.date_input("Início", datetime.now() + timedelta(days=30))
    with col2:
        d_fim = st.date_input("Fim", datetime.now() + timedelta(days=33))

    if st.button("➕ Adicionar à Lista"):
        if h_nome and h_url:
            st.session_state.hoteis_lista.append({
                "nome": h_nome, 
                "url": h_url, 
                "ini": d_ini, 
                "fim": d_fim
            })
            st.success(f"{h_nome} adicionado!")
        else:
            st.error("Preencha o nome e a URL.")

    if st.button("🗑️ Limpar Lista"):
        st.session_state.hoteis_lista = []
        st.rerun()

# EXIBIÇÃO DA FILA
if st.session_state.hoteis_lista:
    st.write("### Hotéis na Fila")
    st.table(pd.DataFrame(st.session_state.hoteis_lista))

    if st.button("🚀 INICIAR COLETA AGORA"):
        install_playwright_stuff()

        async def main_async():
            todos_resultados = []
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
                page = await browser.new_page()
                await stealth(page)

                progresso = st.progress(0)
                status = st.empty()
                
                for i, hotel in enumerate(st.session_state.hoteis_lista):
                    periodos = gerar_periodos_pernoite(hotel["ini"], hotel["fim"])
                    for checkin, checkout in periodos:
                        status.info(f"🔎 Pesquisando {hotel['nome']} | {checkin}")
                        dados = await coletar_dados_booking(page, hotel["nome"], hotel["url"], checkin, checkout)
                        todos_resultados.extend(dados)
                    progresso.progress((i + 1) / len(st.session_state.hoteis_lista))

                await browser.close()
            return todos_resultados

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            resultado = loop.run_until_complete(main_async())
            loop.close()

            if resultado:
                df = pd.DataFrame(resultado)
                st.success("✅ Coleta Finalizada!")
                st.dataframe(df, use_container_width=True)
                st.download_button("📥 Baixar CSV", df.to_csv(index=False), "pesquisa_viagem.csv")
        except Exception as e:
            st.error(f"Erro: {e}")
else:
    st.info("Adicione um hotel na barra lateral para começar.")
