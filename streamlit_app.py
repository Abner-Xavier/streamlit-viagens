import os
import streamlit as st
import asyncio
import re
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
# Importação específica para evitar o erro de 'module not callable'
from playwright import stealth 

# --- CONFIGURAÇÃO DO NAVEGADOR ---
def preparar_navegador():
    if 'navegador_pronto' not in st.session_state:
        with st.spinner("Configurando ambiente do navegador..."):
            os.system("playwright install chromium")
            st.session_state.navegador_pronto = True

def gerar_pernoites(data_ini, data_fim):
    periodos = []
    atual = data_ini
    while atual < data_fim:
        proximo = atual + timedelta(days=1)
        periodos.append((atual.strftime("%Y-%m-%d"), proximo.strftime("%Y-%m-%d")))
        atual = proximo
    return periodos

# --- LÓGICA DE SCRAPING ---
async def coletar_dados(page, hotel_nome, checkin, checkout):
    # Busca direta no Booking usando o nome do hotel
    query = hotel_nome.replace(" ", "+")
    url_busca = f"https://www.booking.com/searchresults.pt-br.html?ss={query}&checkin={checkin}&checkout={checkout}&selected_currency=USD"
    
    try:
        await page.goto(url_busca, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        # Clica no primeiro hotel da lista
        primeiro_hotel = await page.query_selector("div[data-testid='property-card']")
        if primeiro_hotel:
            async with page.expect_popup() as popup_info:
                await primeiro_hotel.query_selector("a[data-testid='title-link']").click()
            hotel_page = await popup_info.value
            await hotel_page.wait_for_load_state("domcontentloaded")
            
            # Extração da tabela de preços
            rows = await hotel_page.query_selector_all("table.hprt-table tbody tr.hprt-table-row")
            resultados = []
            quarto, area = "Desconhecido", None

            for row in rows:
                nome_el = await row.query_selector(".hprt-roomtype-link")
                if nome_el:
                    quarto = (await nome_el.inner_text()).strip()
                    texto = await row.inner_text()
                    m2 = re.search(r"(\d+)\s*(?:m²|sq m)", texto)
                    area = int(m2.group(1)) if m2 else None

                preco_el = await row.query_selector("span[data-testid='price-and-discounted-price'], .bui-price-display__value")
                if preco_el:
                    v_txt = await preco_el.inner_text()
                    v_num = re.search(r"[\d,.]+", v_txt)
                    if v_num:
                        preco_float = float(v_num.group().replace(",", ""))
                        resultados.append({
                            "Hotel_Name": hotel_nome,
                            "Checkin": checkin,
                            "Checkout": checkout,
                            "Room_Name": quarto,
                            "Area_m2": area,
                            "Price_USD": f"$ {preco_float:.2f}"
                        })
            await hotel_page.close()
            return resultados
        return []
    except:
        return []

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="Booking Search Bot", layout="wide")
st.title("🏨 Automação Booking: Pesquisa por Nome")

if "fila_hoteis" not in st.session_state:
    st.session_state.fila_hoteis = []

with st.sidebar:
    st.header("Configurações de Busca")
    nome = st.text_input("Nome do Hotel", placeholder="Ex: Hyatt Regency Lisbon")
    col1, col2 = st.columns(2)
    d_ini = col1.date_input("Início", datetime(2025, 12, 27))
    d_fim = col2.date_input("Fim", datetime(2025, 12, 30))

    if st.button("➕ Adicionar Hotel"):
        if nome:
            st.session_state.fila_hoteis.append({"nome": nome, "ini": d_ini, "fim": d_fim})
            st.rerun()

    if st.button("🗑️ Limpar Lista"):
        st.session_state.fila_hoteis = []
        st.rerun()

# --- EXECUÇÃO ---
if st.session_state.fila_hoteis:
    st.write("### 📋 Hotéis para Pesquisa")
    st.table(pd.DataFrame(st.session_state.fila_hoteis))

    if st.button("🚀 INICIAR PESQUISA AGORA"):
        preparar_navegador()

        async def rodar_scrapers():
            dados_finais = []
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                context = await browser.new_context()
                page = await context.new_page()
                
                # CHAMADA CORRIGIDA: Usa a função importada corretamente
                await stealth(page) 

                progresso = st.progress(0)
                status = st.empty()
                
                for i, hotel in enumerate(st.session_state.fila_hoteis):
                    periodos = gerar_pernoites(hotel["ini"], hotel["fim"])
                    for c_in, c_out in periodos:
                        status.info(f"🔎 Buscando: {hotel['nome']} | {c_in}")
                        data = await coletar_dados(page, hotel['nome'], c_in, c_out)
                        dados_finais.extend(data)
                    progresso.progress((i + 1) / len(st.session_state.fila_hoteis))

                await browser.close()
            return dados_finais

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            resultado = loop.run_until_complete(rodar_scrapers())
            loop.close()

            if resultado:
                st.success("✅ Pesquisa finalizada!")
                df = pd.DataFrame(resultado)
                # Tabela organizada por pernoites (Foto 2)
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("Nenhum dado encontrado.")
        except Exception as e:
            st.error(f"Erro Crítico: {e}")
else:
    st.info("Sua fila está vazia. Adicione hotéis na barra lateral.")
