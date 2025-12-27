import os
import streamlit as st
import asyncio
import re
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
# MUDANÇA AQUI: Importamos a função específica para evitar o erro de 'module'
from playwright_stealth import stealth 

# --- AMBIENTE ---
def preparar_navegador():
    if 'navegador_pronto' not in st.session_state:
        with st.spinner("Configurando Chromium..."):
            os.system("playwright install chromium")
            st.session_state.navegador_pronto = True

def gerar_periodos(data_ini, data_fim):
    periodos = []
    atual = data_ini
    while atual < data_fim:
        proximo = atual + timedelta(days=1)
        periodos.append((atual.strftime("%Y-%m-%d"), proximo.strftime("%Y-%m-%d")))
        atual = proximo
    return periodos

# --- SCRAPER ---
async def extrair_dados(page, hotel_nome, checkin, checkout):
    query = hotel_nome.replace(" ", "+")
    url_busca = f"https://www.booking.com/searchresults.pt-br.html?ss={query}&checkin={checkin}&checkout={checkout}&selected_currency=USD"
    
    try:
        await page.goto(url_busca, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        primeiro_hotel = await page.query_selector("div[data-testid='property-card']")
        if primeiro_hotel:
            async with page.expect_popup() as popup_info:
                await primeiro_hotel.query_selector("a[data-testid='title-link']").click()
            hotel_page = await popup_info.value
            await hotel_page.wait_for_load_state("domcontentloaded")
            
            rows = await hotel_page.query_selector_all("table.hprt-table tbody tr.hprt-table-row")
            dados_dia = []
            quarto, area = "Desconhecido", None

            for row in rows:
                nome_el = await row.query_selector(".hprt-roomtype-link")
                if nome_el:
                    quarto = (await nome_el.inner_text()).strip()
                    txt = await row.inner_text()
                    m2 = re.search(r"(\d+)\s*(?:m²|sq m)", txt)
                    area = int(m2.group(1)) if m2 else None

                preco_el = await row.query_selector("span[data-testid='price-and-discounted-price'], .bui-price-display__value")
                if preco_el:
                    valor_txt = await preco_el.inner_text()
                    valor_num = re.search(r"[\d,.]+", valor_txt)
                    if valor_num:
                        preco_final = float(valor_num.group().replace(",", ""))
                        dados_dia.append({
                            "Hotel_Name": hotel_nome,
                            "Checkin": checkin,
                            "Checkout": checkout,
                            "Room_Name": quarto,
                            "Area_m2": area,
                            "Price_USD": f"$ {preco_final:.2f}",
                            "Qty_Available": 5
                        })
            await hotel_page.close()
            return dados_dia
        return []
    except Exception:
        return []

# --- INTERFACE ---
st.set_page_config(page_title="Booking Search Tool", layout="wide")
st.title("🏨 Automação de Pesquisa Booking")

if "fila" not in st.session_state:
    st.session_state.fila = []

with st.sidebar:
    st.header("Pesquisar Hotel")
    nome_hotel = st.text_input("Nome do Hotel", placeholder="Ex: Hyatt Regency Lisbon")
    c1, c2 = st.columns(2)
    d_ini = c1.date_input("Início", datetime(2025, 12, 27))
    d_fim = c2.date_input("Fim", datetime(2025, 12, 30))

    if st.button("➕ Adicionar"):
        if nome_hotel:
            st.session_state.fila.append({"nome": nome_hotel, "ini": d_ini, "fim": d_fim})
            st.rerun()

    if st.button("🗑️ Limpar"):
        st.session_state.fila = []
        st.rerun()

if st.session_state.fila:
    st.table(pd.DataFrame(st.session_state.fila))

    if st.button("🚀 INICIAR PESQUISA"):
        preparar_navegador()

        async def main():
            resultados = []
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                context = await browser.new_context()
                page = await context.new_page()
                
                # CHAMADA CORRIGIDA: Agora passamos 'page' para a função 'stealth'
                await stealth(page) 

                progresso = st.progress(0)
                for i, h in enumerate(st.session_state.fila):
                    periodos = gerar_periodos(h["ini"], h["fim"])
                    for checkin, checkout in periodos:
                        data = await extrair_dados(page, h['nome'], checkin, checkout)
                        resultados.extend(data)
                    progresso.progress((i + 1) / len(st.session_state.fila))
                await browser.close()
            return resultados

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            final_data = loop.run_until_complete(main())
            loop.close()

            if final_data:
                st.success("✅ Concluído!")
                st.dataframe(pd.DataFrame(final_data), use_container_width=True)
            else:
                st.warning("Nenhum dado encontrado.")
        except Exception as e:
            st.error(f"Erro: {e}")
