import os
import streamlit as st
import asyncio
import re
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from playwright_stealth import stealth

# --- 1. INSTALAÇÃO AUTOMÁTICA DO NAVEGADOR ---
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

# --- 3. SCRAPER DO BOOKING ---
async def extrair_precos(page, hotel_nome, url_origem, checkin, checkout):
    # Limpa a URL de parâmetros antigos para evitar erros
    url_base = url_origem.split('?')[0]
    url = f"{url_base}?checkin={checkin}&checkout={checkout}&group_adults=2&no_rooms=1&selected_currency=USD&lang=en-us"
    
    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)

        rows = await page.query_selector_all("table.hprt-table tbody tr.hprt-table-row")
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
        return dados_dia
    except:
        return []

# --- 4. INTERFACE ---
st.set_page_config(page_title="Booking Search", layout="wide")
st.title("🏨 Automação de Pesquisa Booking")

# Inicializa lista vazia (conforme solicitado)
if "lista_hoteis" not in st.session_state:
    st.session_state.lista_hoteis = []

with st.sidebar:
    st.header("Configurações")
    nome = st.text_input("Nome do Hotel", placeholder="Ex: Hyatt Regency Lisbon")
    link = st.text_input("URL do Booking", placeholder="Cole o link do hotel aqui")
    
    c1, c2 = st.columns(2)
    data_i = c1.date_input("Início", datetime(2025, 12, 27))
    data_f = c2.date_input("Fim", datetime(2025, 12, 30))

    if st.button("➕ Adicionar à Fila"):
        if nome and link:
            st.session_state.lista_hoteis.append({"nome": nome, "url": link, "ini": data_i, "fim": data_f})
            st.rerun()

    if st.button("🗑️ Limpar Tudo"):
        st.session_state.lista_hoteis = []
        st.rerun()

# --- 5. EXECUÇÃO ---
if st.session_state.lista_hoteis:
    st.write("### 📋 Hotéis na Fila")
    st.dataframe(pd.DataFrame(st.session_state.lista_hoteis), use_container_width=True)

    if st.button("🚀 INICIAR PESQUISA"):
        preparar_navegador()

        async def rodar_automacao():
            resultados_finais = []
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                page = await browser.new_page()
                await stealth(page)

                barra = st.progress(0)
                status = st.empty()
                
                for idx, h in enumerate(st.session_state.lista_hoteis):
                    periodos = gerar_periodos(h["ini"], h["fim"])
                    for c_in, c_out in periodos:
                        status.info(f"🔎 Coletando: {h['nome']} | {c_in}")
                        data = await extrair_precos(page, h["nome"], h["url"], c_in, c_out)
                        resultados_finais.extend(data)
                    barra.progress((idx + 1) / len(st.session_state.lista_hoteis))

                await browser.close()
            return resultados_finais

        # Gerenciamento do loop para evitar erros de thread
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            final_df_data = loop.run_until_complete(rodar_automacao())
            loop.close()

            if final_df_data:
                st.success("✅ Pesquisa concluída!")
                df = pd.DataFrame(final_df_data)
                # Exibe a tabela formatada exatamente como na FOTO 2
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("Nenhum preço encontrado. Verifique se o link está correto.")
        except Exception as e:
            st.error(f"Erro na pesquisa: {e}")
else:
    st.info("Utilize a barra lateral para adicionar hotéis.")
