import streamlit as st
import asyncio
import os
import re
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import playwright_stealth

# --- FUNÇÃO DE INSTALAÇÃO (Resolve o erro da Foto 1) ---
def setup_playwright():
    """Garante que o navegador esteja instalado no servidor do Streamlit."""
    os.system("playwright install chromium")

# --- LÓGICA DE NEGÓCIO: GERAR PERNOITES (Igual à Foto 2) ---
def gerar_periodos_pernoite(start_date, end_date):
    periodos = []
    atual = start_date
    while atual < end_date:
        proximo = atual + timedelta(days=1)
        periodos.append((atual.strftime("%Y-%m-%d"), proximo.strftime("%Y-%m-%d")))
        atual = proximo
    return periodos

async def coletar_dados_booking(page, hotel_name, url_base, checkin, checkout):
    url = f"{url_base}?checkin={checkin}&checkout={checkout}&group_adults=2&no_rooms=1&selected_currency=USD&lang=en-us"
    
    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000) # Espera carregar os preços

        rows = await page.query_selector_all("table.hprt-table tbody tr.hprt-table-row")
        resultados = []
        
        # Variáveis para manter o nome do quarto entre linhas da mesma categoria
        quarto_atual = "Desconhecido"
        area_atual = None

        for row in rows:
            nome_el = await row.query_selector(".hprt-roomtype-link")
            if nome_el:
                quarto_atual = (await nome_el.inner_text()).strip()
                texto_linha = await row.inner_text()
                area_match = re.search(r"(\d+)\s*(?:m²|sq m)", texto_linha)
                area_atual = int(area_match.group(1)) if area_match else None

            preco_el = await row.query_selector(".bui-price-display__value, .prco-valign-middle-helper")
            if preco_el:
                preco_raw = await preco_el.inner_text()
                preco_num = re.search(r"[\d,.]+", preco_raw.replace("$", ""))
                
                if preco_num:
                    resultados.append({
                        "Hotel_Name": hotel_name,
                        "Checkin": checkin,
                        "Checkout": checkout,
                        "Room_Name": quarto_atual,
                        "Area_m2": area_atual,
                        "Price_USD": float(preco_num.group().replace(",", "")),
                        "Qty_Available": 5 # Pode ser extraído do select se necessário
                    })
        return resultados
    except Exception as e:
        return []

# --- INTERFACE STREAMLIT ---
st.set_page_config(page_title="Travel Bot", layout="wide")
st.title("🏨 Automação de Pesquisa Booking")

if 'hoteis' not in st.session_state:
    st.session_state.hoteis = []

with st.sidebar:
    st.header("Configurações")
    nome = st.text_input("Nome do Hotel", "Hyatt Regency Lisbon")
    link = st.text_input("URL do Booking")
    data_ini = st.date_input("Data Início", datetime(2025, 12, 27))
    data_fim = st.date_input("Data Fim", datetime(2025, 12, 30))
    
    if st.button("➕ Adicionar à Lista"):
        st.session_state.hoteis.append({"nome": nome, "url": link, "ini": data_ini, "fim": data_fim})

if st.session_state.hoteis:
    st.write("### Hotéis na Fila")
    st.table(pd.DataFrame(st.session_state.hoteis))

    if st.button("🚀 INICIAR AUTOMAÇÃO"):
        setup_playwright() # Instala o navegador antes de começar
        
        async def main():
            todos_dados = []
            async with async_playwright() as p:
                # O segredo para rodar em nuvem: --no-sandbox
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
                page = await browser.new_page()
                await playwright_stealth.stealth(page)
                
                progresso = st.progress(0)
                status = st.empty()
                
                total_tarefas = len(st.session_state.hoteis)
                for idx, hotel in enumerate(st.session_state.hoteis):
                    periodos = gerar_periodos_pernoite(hotel['ini'], hotel['fim'])
                    
                    for checkin, checkout in periodos:
                        status.info(f"Pesquisando {hotel['nome']}: {checkin} até {checkout}")
                        dados = await coletar_dados_booking(page, hotel['nome'], hotel['url'], checkin, checkout)
                        todos_dados.extend(dados)
                    
                    progresso.progress((idx + 1) / total_tarefas)
                
                await browser.close()
            return todos_dados

        resultado_final = asyncio.run(main())
        
        if resultado_final:
            df = pd.DataFrame(resultado_final)
            st.success("Busca finalizada!")
            st.dataframe(df, use_container_width=True) # Exibe igual à Foto 2
            st.download_button("📥 Baixar CSV", df.to_csv(index=False), "pesquisa_booking.csv")
