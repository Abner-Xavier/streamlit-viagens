import os
import streamlit as st
import asyncio
import re
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from playwright_stealth import stealth  # IMPORTAÇÃO CORRETA

# --- 1. CONFIGURAÇÃO DE AMBIENTE ---
def preparar_navegador():
    if 'navegador_pronto' not in st.session_state:
        with st.spinner("Instalando componentes do Chrome no servidor..."):
            os.system("playwright install chromium")
            st.session_state.navegador_pronto = True

def gerar_periodos(data_ini, data_fim):
    """Gera fatias de 1 noite para cada estadia conforme a FOTO 2"""
    periodos = []
    atual = data_ini
    while atual < data_fim:
        proximo = atual + timedelta(days=1)
        periodos.append((atual.strftime("%Y-%m-%d"), proximo.strftime("%Y-%m-%d")))
        atual = proximo
    return periodos

# --- 2. LÓGICA DE BUSCA POR NOME ---
async def extrair_dados_booking(page, hotel_nome, checkin, checkout):
    # Pesquisa direta pelo nome na URL do Booking
    query = hotel_nome.replace(" ", "+")
    url_busca = f"https://www.booking.com/searchresults.pt-br.html?ss={query}&checkin={checkin}&checkout={checkout}&group_adults=2&no_rooms=1&selected_currency=USD"
    
    try:
        await page.goto(url_busca, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Localiza o primeiro hotel na lista de resultados
        primeiro_hotel = await page.query_selector("div[data-testid='property-card']")
        if primeiro_hotel:
            # Clica no link do título que abre uma nova aba (popup)
            async with page.expect_popup() as popup_info:
                await primeiro_hotel.query_selector("a[data-testid='title-link']").click()
            hotel_page = await popup_info.value
            await hotel_page.wait_for_load_state("domcontentloaded")
            
            # Captura as linhas da tabela de preços
            rows = await hotel_page.query_selector_all("table.hprt-table tbody tr.hprt-table-row")
            dados_dia = []
            quarto_atual, area_atual = "Desconhecido", None

            for row in rows:
                # Extrai nome do quarto e área
                nome_el = await row.query_selector(".hprt-roomtype-link")
                if nome_el:
                    quarto_atual = (await nome_el.inner_text()).strip()
                    texto = await row.inner_text()
                    area_m = re.search(r"(\d+)\s*(?:m²|sq m)", texto)
                    area_atual = int(area_m.group(1)) if area_m else None

                # Extrai o preço
                preco_el = await row.query_selector("span[data-testid='price-and-discounted-price'], .bui-price-display__value")
                if preco_el:
                    txt_preco = await preco_el.inner_text()
                    valor = re.search(r"[\d,.]+", txt_preco)
                    if valor:
                        dados_dia.append({
                            "Hotel_Name": hotel_nome,
                            "Checkin": checkin,
                            "Checkout": checkout,
                            "Room_Name": quarto_atual,
                            "Area_m2": area_atual,
                            "Price_USD": float(valor.group().replace(",", "")),
                            "Qty_Available": 5
                        })
            await hotel_page.close()
            return dados_dia
        return []
    except Exception:
        return []

# --- 3. INTERFACE STREAMLIT ---
st.set_page_config(page_title="Booking Search Tool", layout="wide")
st.title("🏨 Automação de Pesquisa Booking")

# Inicializa lista de hotéis vazia
if "hoteis_fila" not in st.session_state:
    st.session_state.hoteis_fila = []

with st.sidebar:
    st.header("Configurações")
    novo_hotel = st.text_input("Nome do Hotel", placeholder="Ex: Hyatt Regency Lisbon")
    
    col1, col2 = st.columns(2)
    d_ini = col1.date_input("Data Início", datetime(2025, 12, 27))
    d_fim = col2.date_input("Data Fim", datetime(2025, 12, 30))

    if st.button("➕ Adicionar Hotel"):
        if novo_hotel:
            st.session_state.hoteis_fila.append({"nome": novo_hotel, "ini": d_ini, "fim": d_fim})
            st.rerun()

    if st.button("🗑️ Limpar Lista"):
        st.session_state.hoteis_fila = []
        st.rerun()

# --- 4. EXECUÇÃO DA AUTOMAÇÃO ---
if st.session_state.hoteis_fila:
    st.write("### 📋 Hotéis na Fila")
    st.table(pd.DataFrame(st.session_state.hoteis_fila))

    if st.button("🚀 INICIAR PESQUISA"):
        preparar_navegador()

        async def rodar_scrapers():
            todos_resultados = []
            async with async_playwright() as p:
                # Launch com flags de segurança para Cloud
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                context = await browser.new_context()
                page = await context.new_page()
                
                # CHAMADA CORRIGIDA: stealth(page) em vez de module(page)
                await stealth(page) 

                barra = st.progress(0)
                status = st.empty()
                
                for idx, hotel in enumerate(st.session_state.hoteis_fila):
                    periodos = gerar_periodos(hotel["ini"], hotel["fim"])
                    for c_in, c_out in periodos:
                        status.info(f"🔎 Buscando: {hotel['nome']} | {c_in}")
                        data = await extrair_dados_booking(page, hotel['nome'], c_in, c_out)
                        todos_resultados.extend(data)
                    
                    barra.progress((idx + 1) / len(st.session_state.hoteis_fila))

                await browser.close()
            return todos_resultados

        # Gerenciamento de Loop assíncrono para evitar erros de thread
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            final_data = loop.run_until_complete(rodar_scrapers())
            loop.close()

            if final_data:
                st.success("✅ Pesquisa concluída com sucesso!")
                df = pd.DataFrame(final_data)
                # Exibe a tabela formatada
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("Nenhum dado encontrado. Verifique se o nome do hotel está correto.")
        except Exception as e:
            st.error(f"Erro inesperado: {e}")
else:
    st.info("Utilize a barra lateral para adicionar o nome dos hotéis que deseja pesquisar.")
