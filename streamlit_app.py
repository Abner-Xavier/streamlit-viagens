import os
import streamlit as st
import asyncio
import re
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import playwright_stealth

# --- PASSO CRUCIAL: Instalação do Navegador no Servidor ---
def install_browser():
    if not os.path.exists("/home/adminuser/.cache/ms-playwright"):
        with st.spinner("Instalando navegadores (isso leva 1 minuto)..."):
            os.system("playwright install chromium")

# --- LÓGICA DE NEGÓCIO ---
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
        await page.wait_for_timeout(3000)
        
        rows = await page.query_selector_all("table.hprt-table tbody tr.hprt-table-row")
        resultados = []
        quarto_atual, area_atual = "Desconhecido", None

        for row in rows:
            nome_el = await row.query_selector(".hprt-roomtype-link")
            if nome_el:
                quarto_atual = (await nome_el.inner_text()).strip()
                texto = await row.inner_text()
                area_match = re.search(r"(\d+)\s*(?:m²|sq m)", texto)
                area_atual = int(area_match.group(1)) if area_match else None

            preco_el = await row.query_selector(".bui-price-display__value, .prco-valign-middle-helper")
            if preco_el:
                preco_raw = await preco_el.inner_text()
                preco_num = re.search(r"[\d,.]+", preco_raw)
                if preco_num:
                    resultados.append({
                        "Hotel_Name": hotel_name,
                        "Checkin": checkin,
                        "Checkout": checkout,
                        "Room_Name": quarto_atual,
                        "Area_m2": area_atual,
                        "Price_USD": float(preco_num.group().replace(",", "")),
                        "Qty_Available": 5
                    })
        return resultados
    except Exception:
        return []

# --- INTERFACE ---
st.set_page_config(page_title="Travel Bot", layout="wide")
st.title("🏨 Automação de Pesquisa Booking")

if "hoteis" not in st.session_state:
    st.session_state.hoteis = []

# Menu Lateral
with st.sidebar:
    st.header("Configurações")
    nome = st.text_input("Nome do Hotel", "Grand Hyatt Istanbul")
    link = st.text_input("URL do Booking")
    data_ini = st.date_input("Data Início", datetime(2025, 12, 27))
    data_fim = st.date_input("Data Fim", datetime(2025, 12, 30))

    if st.button("➕ Adicionar à Lista"):
        st.session_state.hoteis.append({"nome": nome, "url": link, "ini": data_ini, "fim": data_fim})

if st.session_state.hoteis:
    st.subheader("📋 Hotéis na fila")
    st.dataframe(pd.DataFrame(st.session_state.hoteis), use_container_width=True)

    if st.button("🚀 INICIAR AUTOMAÇÃO"):
        install_browser() # Garante o navegador antes de rodar

        async def main():
            todos_dados = []
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
                page = await browser.new_page()
                await playwright_stealth.stealth(page)

                progresso = st.progress(0)
                status = st.empty()

                for idx, hotel in enumerate(st.session_state.hoteis):
                    periodos = gerar_periodos_pernoite(hotel["ini"], hotel["fim"])
                    for checkin, checkout in periodos:
                        status.info(f"🔎 Coletando {hotel['nome']} | {checkin}")
                        dados = await coletar_dados_booking(page, hotel["nome"], hotel["url"], checkin, checkout)
                        todos_dados.extend(dados)
                    progresso.progress((idx + 1) / len(st.session_state.hoteis))

                await browser.close()
            return todos_dados

        # Execução segura do Loop Async
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            resultado_final = loop.run_until_complete(main())

            if resultado_final:
                df = pd.DataFrame(resultado_final)
                st.success("✅ Busca finalizada!")
                st.dataframe(df, use_container_width=True)
                st.download_button("📥 Baixar CSV", df.to_csv(index=False), "pesquisa.csv")
            else:
                st.warning("Nenhum dado encontrado.")
        except Exception as e:
            st.error(f"Erro na automação: {e}")
