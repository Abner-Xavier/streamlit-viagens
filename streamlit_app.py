import streamlit as st
import asyncio
import re
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# --------------------------------------------------
# CONFIG STREAMLIT
# --------------------------------------------------
st.set_page_config(
    page_title="Booking Search Bot (USA)",
    layout="wide"
)

st.title("🏨 Booking Automation — USA | USD")

# --------------------------------------------------
# FUNÇÕES AUXILIARES
# --------------------------------------------------
def gerar_pernoites(data_ini, data_fim):
    periodos = []
    atual = data_ini
    while atual < data_fim:
        prox = atual + timedelta(days=1)
        periodos.append(
            (atual.strftime("%Y-%m-%d"), prox.strftime("%Y-%m-%d"))
        )
        atual = prox
    return periodos


async def coletar_dados(page, hotel_nome, checkin, checkout):
    resultados = []

    query = hotel_nome.replace(" ", "+")

    url = (
        "https://www.booking.com/searchresults.en-us.html"
        f"?ss={query}"
        "&dest_type=country"
        "&dest_id=20088325"
        f"&checkin={checkin}"
        f"&checkout={checkout}"
        "&group_adults=2"
        "&no_rooms=1"
        "&selected_currency=USD"
    )

    try:
        await page.goto(url, timeout=60000)
        await page.wait_for_timeout(3000)

        card = await page.query_selector("div[data-testid='property-card']")
        if not card:
            return resultados

        link = await card.query_selector("a[data-testid='title-link']")
        href = await link.get_attribute("href")

        hotel_page = await page.context.new_page()
        await hotel_page.goto("https://www.booking.com" + href, timeout=60000)
        await hotel_page.wait_for_load_state("domcontentloaded")
        await hotel_page.wait_for_timeout(3000)

        rows = await hotel_page.query_selector_all(
            "table.hprt-table tbody tr.hprt-table-row"
        )

        quarto_atual = "Unknown"
        area_atual = None

        for row in rows:
            nome_el = await row.query_selector(".hprt-roomtype-link")
            if nome_el:
                quarto_atual = (await nome_el.inner_text()).strip()
                texto = await row.inner_text()
                m2 = re.search(r"(\d+)\s*(?:m²|sq m)", texto)
                area_atual = int(m2.group(1)) if m2 else None

            preco_el = await row.query_selector(
                "span[data-testid='price-and-discounted-price'], .bui-price-display__value"
            )

            if preco_el:
                preco_txt = await preco_el.inner_text()
                match = re.search(r"[\d.,]+", preco_txt)

                if match:
                    valor = match.group()
                    valor = valor.replace(",", "")
                    preco = float(valor)

                    resultados.append({
                        "Hotel": hotel_nome,
                        "Check-in": checkin,
                        "Check-out": checkout,
                        "Room": quarto_atual,
                        "Area_m2": area_atual,
                        "Price_USD": round(preco, 2)
                    })

        await hotel_page.close()
        return resultados

    except:
        return resultados


async def rodar_scrapers(hoteis):
    dados_finais = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage"
            ]
        )

        context = await browser.new_context(
            locale="en-US",
            timezone_id="America/New_York",
            viewport={"width": 1280, "height": 800}
        )

        progresso = st.progress(0.0)
        status = st.empty()

        for i, hotel in enumerate(hoteis):
            page = await context.new_page()

            periodos = gerar_pernoites(hotel["ini"], hotel["fim"])
            for c_in, c_out in periodos:
                status.info(f"🔎 {hotel['nome']} | {c_in}")
                dados = await coletar_dados(
                    page, hotel["nome"], c_in, c_out
                )
                dados_finais.extend(dados)

            await page.close()
            progresso.progress((i + 1) / len(hoteis))

        await browser.close()

    return dados_finais


# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------
if "fila_hoteis" not in st.session_state:
    st.session_state.fila_hoteis = []


# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------
with st.sidebar:
    st.header("Search settings (USA)")

    nome = st.text_input("Hotel name")
    col1, col2 = st.columns(2)

    d_ini = col1.date_input("Check-in", datetime(2025, 12, 27))
    d_fim = col2.date_input("Check-out", datetime(2025, 12, 30))

    if st.button("➕ Add hotel"):
        if nome:
            st.session_state.fila_hoteis.append({
                "nome": nome,
                "ini": d_ini,
                "fim": d_fim
            })
            st.rerun()

    if st.button("🗑️ Clear list"):
        st.session_state.fila_hoteis = []
        st.rerun()


# --------------------------------------------------
# EXECUÇÃO
# --------------------------------------------------
if st.session_state.fila_hoteis:
    st.subheader("📋 Hotels queued")
    st.dataframe(
        pd.DataFrame(st.session_state.fila_hoteis),
        use_container_width=True
    )

    if st.button("🚀 START SEARCH"):
        with st.spinner("Searching Booking.com (USA, USD)..."):
            resultado = asyncio.run(
                rodar_scrapers(st.session_state.fila_hoteis)
            )

        if resultado:
            df = pd.DataFrame(resultado)
            st.success("✅ Search completed")
            st.dataframe(df, use_container_width=True)

            st.download_button(
                "⬇️ Download CSV",
                df.to_csv(index=False),
                file_name="booking_usa_usd.csv",
                mime="text/csv"
            )
        else:
            st.warning("No data found.")
else:
    st.info("Add hotels in the sidebar to start.")
