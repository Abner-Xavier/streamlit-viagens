import streamlit as st
import asyncio
from datetime import date
from playwright.async_api import async_playwright


st.set_page_config(page_title="Busca de Hotéis (USD)", layout="centered")

st.title("🏨 Busca automática de hotéis (USD)")
st.write("Digite apenas o nome do hotel. A busca é automática no Booking.com (EUA).")


# -----------------------------
# FUNÇÃO ASYNC DE SCRAPING
# -----------------------------
async def buscar_hotel(hotel, checkin, checkout):
    resultados = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        context = await browser.new_context(
            locale="en-US",
            timezone_id="America/New_York",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )

        page = await context.new_page()

        url = (
            "https://www.booking.com/searchresults.html"
            f"?ss={hotel}"
            f"&checkin={checkin}"
            f"&checkout={checkout}"
            "&selected_currency=USD"
        )

        await page.goto(url, timeout=60000)
        await page.wait_for_timeout(6000)

        cards = await page.query_selector_all('[data-testid="property-card"]')

        for card in cards[:5]:
            nome_el = await card.query_selector('[data-testid="title"]')
            preco_el = await card.query_selector('[data-testid="price-and-discounted-price"]')

            nome = await nome_el.inner_text() if nome_el else "N/A"
            preco = await preco_el.inner_text() if preco_el else "N/A"

            resultados.append({
                "Hotel": nome.strip(),
                "Preço (USD)": preco.strip()
            })

        await browser.close()

    return resultados


# -----------------------------
# INTERFACE STREAMLIT
# -----------------------------
hotel = st.text_input("Nome do hotel", placeholder="Ex: Hilton New York Times Square")

checkin = st.date_input("Check-in", min_value=date.today())
checkout = st.date_input("Check-out", min_value=date.today())

buscar = st.button("🔍 Buscar preços")

if buscar:
    if not hotel:
        st.error("Digite o nome do hotel.")
    elif checkin >= checkout:
        st.error("A data de check-out deve ser depois do check-in.")
    else:
        with st.spinner("Buscando hotéis..."):
            resultado = asyncio.run(
                buscar_hotel(
                    hotel,
                    checkin.strftime("%Y-%m-%d"),
                    checkout.strftime("%Y-%m-%d")
                )
            )

        if resultado:
            st.success("Resultados encontrados:")
            st.table(resultado)
        else:
            st.warning("Nenhum resultado encontrado.")
