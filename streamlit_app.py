import os
import streamlit as st
import asyncio
import re
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from playwright_stealth import stealth

# --- 1. INSTALAÇÃO DO NAVEGADOR ---
def preparar_navegador():
    if 'navegador_pronto' not in st.session_state:
        with st.spinner("Configurando componentes do Chrome..."):
            os.system("playwright install chromium")
            st.session_state.navegador_pronto = True

# --- 2. GERAÇÃO DE PERNOITES (FOTO 2) ---
def gerar_periodos(data_ini, data_fim):
    periodos = []
    atual = data_ini
    while atual < data_fim:
        proximo = atual + timedelta(days=1)
        periodos.append((atual.strftime("%Y-%m-%d"), proximo.strftime("%Y-%m-%d")))
        atual = proximo
    return periodos

# --- 3. SCRAPER DO BOOKING (BUSCA POR NOME) ---
async def extrair_precos_por_nome(page, hotel_nome, checkin, checkout):
    # URL de busca que tenta localizar o hotel pelo nome digitado
    search_query = hotel_nome.replace(" ", "+")
    url = f"https://www.booking.com/searchresults.pt-br.html?ss={search_query}&checkin={checkin}&checkout={checkout}&group_adults=2&no_rooms=1&selected_currency=USD"
    
    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Tenta encontrar o primeiro resultado de hotel na lista de busca
        first_hotel = await page.query_selector("div[data-testid='property-card']")
        if first_hotel:
            # Clica no primeiro hotel encontrado para abrir a página de detalhes
            async with page.expect_popup() as popup_info:
                await first_hotel.query_selector("a[data-testid='title-link']").click()
            hotel_page = await popup_info.value
            await hotel_page.wait_for_load_state("domcontentloaded")
            
            # Coleta os dados na página do hotel aberta
            rows = await hotel_page.query_selector_all("table.hprt-table tbody tr.hprt-table-row")
            dados_dia = []
            quarto_nome, area = "Desconhecido", None

            for row in rows:
                nome_el = await row.query_selector(".hprt-roomtype-link")
                if nome_el:
                    quarto_nome = (await nome_el.inner_text()).strip()
                    texto = await row.inner_text()
                    area_m = re.search(r"(\d+)\s*(?:m²|sq m)", texto)
                    area = int(area_m.group(1)) if area_m else None

                preco_el = await row.query_selector("span[data-testid='price-and-discounted-price'], .bui-price-display__value")
                if preco_el:
                    txt_preco = await preco_el.inner_text()
                    valor = re.search(r"[\d,.]+", txt_preco)
                    if valor:
                        dados_dia.append({
                            "Hotel_Name": hotel_nome,
                            "Checkin": checkin,
                            "Checkout": checkout,
                            "Room_Name": quarto_nome,
                            "Area_m2": area,
                            "Price_USD": float(valor.group().replace(",", "")),
                            "Qty_Available": 5
                        })
            await hotel_page.close()
            return dados_dia
        return []
    except:
        return []

# --- 4. INTERFACE ---
st.set_page_config(page_title="Booking Search", layout="wide")
st.title("🏨 Automação de Pesquisa Booking")

# Inicializa lista vazia
if "lista_hoteis" not in st.session_state:
    st.session_state.lista_hoteis = []

with st.sidebar:
    st.header("Configurações")
    # Agora apenas o nome é necessário
    nome_hotel = st.text_input("Nome do Hotel", placeholder="Ex: Hyatt Regency Lisbon")
    
    c1, c2 = st.columns(2)
    data_i = c1.date_input("Início", datetime(2025, 12, 27))
    data_f = c2.date_input("Fim", datetime(2025, 12, 30))

    if st.button("➕ Adicionar à Fila"):
        if nome_hotel:
            st.session_state.lista_hoteis.append({"nome": nome_hotel, "ini": data_i, "fim": data_f})
            st.rerun()

    if st.button("🗑️ Limpar Tudo"):
        st.session_state.lista_hoteis = []
        st.rerun()

# --- 5. EXECUÇÃO ---
if st.session_state.lista_hoteis:
    st.write("### 📋 Hotéis na Fila")
    st.table(pd.DataFrame(st.session_state.lista_hoteis))

    if st.button("🚀 INICIAR PESQUISA"):
        preparar_navegador()

        async def rodar_automacao():
            resultados_finais = []
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
                context = await browser.new_context()
                page = await context.new_page()
                await stealth(page)

                barra = st.progress(0)
                status = st.empty()
                
                for idx, h in enumerate(st.session_state.lista_hoteis):
                    periodos = gerar_periodos(h["ini"], h["fim"])
                    for c_in, c_out in periodos:
                        status.info(f"🔎 Buscando no Booking: {h['nome']} | {c_in}")
                        data = await extrair_precos_por_nome(page, h['nome'], c_in, c_out)
                        resultados_finais.extend(data)
                    barra.progress((idx + 1) / len(st.session_state.lista_hoteis))

                await browser.close()
            return resultados_finais

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            final_df_data = loop.run_until_complete(rodar_automacao())
            loop.close()

            if final_df_data:
                st.success("✅ Pesquisa concluída!")
                df = pd.DataFrame(final_df_data)
                # Exibe a tabela conforme o exemplo
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("Não foi possível encontrar o hotel ou os preços. Tente ser mais específico no nome.")
        except Exception as e:
            st.error(f"Erro na pesquisa: {e}")
