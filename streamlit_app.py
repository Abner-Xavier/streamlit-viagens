import streamlit as st
from datetime import date
from playwright.sync_api import sync_playwright


st.set_page_config(page_title="Busca de Hotéis (USD)", layout="centered")
st.title("🏨 Busca automática de hotéis (USD)")
st.write("Digite o nome do hotel. Busca direta no Booking.com (USD).")


def buscar_hotel(hotel, checkin, checkout):
    resultados = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        context = browser.new_context(
            locale="en-US",
            timezone_id="America/New_York",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )

        page = context.new_page()

        url = (
            "https://www.booking.com/searchresults.html"
            f"?ss={hotel.replace(' ', '+')}"
            f"&checkin={checkin}"
            f"&checkout={checkout}"
            "&group_adults=2"
            "&no_rooms=1"
            "&selected_currency=USD"
            "&lang=en-us"
        )

        page.goto(url, timeout=60000)
        page.wait_for_timeout(6000)

        cards = page.query_selector_all('[data-testid="property-card"]')

        for card in cards[:5]:
            nome_el = card.query_selector('[data-testid="title"]')
            preco_el = card.query_selector('[data-testid="price-and-discounted-price"]')

            nome = nome_el.inner_text().strip() if nome_el else "N/A"
            preco = preco_el.inner_text().strip() if preco_el else "N/A"

            resultados.append({
                "Hotel": nome,
                "Preço (USD)": preco
            })

        browser.close()

    return resultados


hotel = st.text_input("Nome do hotel", placeholder="Ex: Hilton New York Times Square")
checkin = st.date_input("Check-in", min_value=date.today())
checkout = st.date_input("Check-out", min_value=date.today())

if st.button("🔍 Buscar preços"):
    if not hotel:
        st.error("Digite o nome do hotel.")
    elif checkin >= checkout:
        st.error("Check-out deve ser depois do check-in.")
    else:
        with st.spinner("Buscando hotéis..."):
            resultado = buscar_hotel(
                hotel,
                checkin.strftime("%Y-%m-%d"),
                checkout.strftime("%Y-%m-%d")
            )

        if resultado:
            st.success("Resultados encontrados:")
            st.table(resultado)
        else:
            st.warning("Nenhum resultado encontrado.")
