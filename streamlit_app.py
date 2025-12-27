import streamlit as st
import asyncio
import re
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright


# -------------------------------------------------
# STEALTH MANUAL (ESTÁVEL – SEM BIBLIOTECA EXTERNA)
# -------------------------------------------------
async def aplicar_stealth(page):
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    """)


# -------------------------------------------------
# UTILIDADES
# -------------------------------------------------
def gerar_periodos(data_ini, data_fim):
    periodos = []
    atual = data_ini
    while atual < data_fim:
        proximo = atual + timedelta(days=1)
        periodos.append(
            (atual.strftime("%Y-%m-%d"), proximo.strftime("%Y-%m-%d"))
        )
        atual = proximo
    return periodos


# -------------------------------------------------
# SCRAPER BOOKING (USD GARANTIDO)
# -------------------------------------------------
async def extrair_dados_booking(page, hotel_nome, checkin, checkout):
    query = hotel_nome.replace(" ", "+")
    url = (
        "https://www.booking.com/searchresults.en-us.html"
        f"?ss={query}"
        f"&checkin={checkin}"
        f"&checkout={checkout}"
        "&group_adults=2"
        "&no_rooms=1"
        "&selected_currency=USD"
    )

    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        card = await page.query_selector("div[data-testid='property-card']")
        if not card:
            return []

        async with page.expect_popup() as popup:
            await card.query_selector("a[data-testid='title-link']").click()

        hotel_page = await popup.value
        await hotel_page.wait_for_load_state("domcontentloaded")
        await hotel_page.wait_for_timeout(3000)

        rows = await hotel_page.query_selector_all(
            "table.hprt-table tbody tr.hprt-table-row"
        )

        resultados = []
        quarto_atual = "Desconhecido"
        area_atual = None

        for row in rows:
            nome_el = await row.query_selector(".hprt-roomtype-link")
            if nome_el:
                quarto_atual = (await nome_el.inner_text()).strip()
                texto = await row.inner_text()
                area_m = re.search(r"(\d+)\s*(?:m²|sq m)", texto)
                area_atual = int(area_m.group(1)) if area_m else None

            preco_el = await row.query_selector(
                "span[data-testid='price-and-discounted-price'], .bui-price-display__value"
            )

            if preco_el:
                txt_preco = await preco_el.inner_text()

                # GARANTE USD
                if "$" not in txt_preco and "USD" not in txt_preco:
                    continue

                valor = re.search(r"[\d,.]+", txt_preco)
                if valor:
                    resultados.append({
                        "Hotel_Name": hotel_nome,
                        "Checkin": checkin,
                        "Checkout": checkout,
                        "Room_Name": quarto_atual,
                        "Area_m2": area_atual,
                        "Price_USD": float(valor.group().replace(",", "")),
                        "Currency": "USD",
                        "Qty_Available": 5
                    })

        await hotel_page.close()
        return resultados

    except Exception:
        return []


# -------------------------------------------------
# STREAMLIT UI
# -------------------------------------------------
st.set_page_config(page_title="Booking USD Search", layout="wide")
st.title("🏨 Pesquisa Booking – Valores em Dólar (USD)")

if "hoteis_fila" not in st.session_state:
    st.session_state.hoteis_fila = []

with st.sidebar:
    st.header("Configurações")

    nome_hotel = st.text_input("Nome do Hotel", "Hyatt Regency Lisbon")

    col1, col2 = st.columns(2)
    data_ini = col1.date_input("Data Início", datetime(2025, 12, 27))
    data_fim = col2.date_input("Data Fim", datetime(2025, 12, 30))

    if st.button("➕ Adicionar Hotel"):
        st.session_state.hoteis_fila.append({
            "nome": nome_hotel,
            "ini": data_ini,
            "fim": data_fim
        })
        st.rerun()

    if st.button("🗑️ Limpar Lista"):
        st.session_state.hoteis_fila = []
        st.rerun()


# -------------------------------------------------
# EXECUÇÃO
# -------------------------------------------------
if st.session_state.hoteis_fila:
    st.subheader("📋 Hotéis na fila")
    st.dataframe(pd.DataFrame(st.session_state.hoteis_fila), use_container_width=True)

    if st.button("🚀 INICIAR PESQUISA"):

        async def executar():
            resultados = []

            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--single-process"
                    ]
                )

                context = await browser.new_context(
                    locale="en-US",
                    timezone_id="America/New_York"
                )

                page = await context.new_page()
                await aplicar_stealth(page)

                barra = st.progress(0)
                status = st.empty()
                total = len(st.session_state.hoteis_fila)

                for idx, hotel in enumerate(st.session_state.hoteis_fila):
                    periodos = gerar_periodos(hotel["ini"], hotel["fim"])
                    for checkin, checkout in periodos:
                        status.info(f"🔎 {hotel['nome']} | {checkin}")
                        dados = await extrair_dados_booking(
                            page, hotel["nome"], checkin, checkout
                        )
                        resultados.extend(dados)

                    barra.progress((idx + 1) / total)

                await browser.close()

            return resultados

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        dados_finais = loop.run_until_complete(executar())
        loop.close()

        if dados_finais:
            st.success("✅ Pesquisa concluída!")
            df = pd.DataFrame(dados_finais)
            st.dataframe(df, use_container_width=True)
            st.download_button(
                "📥 Baixar CSV (USD)",
                df.to_csv(index=False),
                "booking_usd.csv"
            )
        else:
            st.warning("Nenhum dado encontrado.")
else:
    st.info("Adicione hotéis para iniciar a pesquisa.")
