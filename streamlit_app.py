import streamlit as st
import asyncio
from datetime import date
from playwright.async_api import async_playwright
import pandas as pd

st.set_page_config(
    page_title="Booking Automation — USA | USD",
    layout="wide"
)

st.title("🏨 Booking Automation — USA | USD")

# ==============================
# UI
# ==============================
with st.sidebar:
    st.header("Search settings (USA)")

    hotel_name = st.text_input(
        "Hotel name",
        value="Hilton Sao Paulo Morumbi"
    )

    col1, col2 = st.columns(2)
    with col1:
        checkin = st.date_input("Check-in", value=date(2025, 12, 30))
    with col2:
        checkout = st.date_input("Check-out", value=date(2026, 1, 3))

    add = st.button("➕ Add hotel")
    clear = st.button("🗑 Clear list")

if "hotels" not in st.session_state:
    st.session_state.hotels = []

if add:
    st.session_state.hotels.append({
        "nome": hotel_name,
        "ini": str(checkin),
        "fim": str(checkout)
    })

if clear:
    st.session_state.hotels = []

st.subheader("📋 Hotels queued")

if st.session_state.hotels:
    df = pd.DataFrame(st.session_state.hotels)
    st.dataframe(df, use_container_width=True)
else:
    st.info("No hotels added")

# ==============================
# Playwright Scraper
# ==============================
async def buscar_booking(hotel, checkin, checkout):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        context = await browser.new_context(
            locale="en-US",
            timezone_id="America/New_York",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9"
            }
        )

        page = await context.new_page()

        url = (
            "https://www.booking.com/searchresults.html"
            f"?ss={hotel.replace(' ', '+')}"
            f"&checkin_year={checkin[:4]}"
            f"&checkin_month={checkin[5:7]}"
            f"&checkin_monthday={checkin[8:10]}"
            f"&checkout_year={checkout[:4]}"
            f"&checkout_month={checkout[5:7]}"
            f"&checkout_monthday={checkout[8:10]}"
            "&group_adults=2"
            "&group_children=0"
            "&no_rooms=1"
            "&selected_currency=USD"
            "&lang=en-us"
        )

        await page.goto(url, timeout=60000)
        await page.wait_for_timeout(5000)

        hotels = await page.locator('[data-testid="property-card"]').count()

        await browser.close()

        return {
            "hotel": hotel,
            "found_results": hotels,
            "currency": "USD",
            "region": "USA"
        }

# ==============================
# Runner seguro para Streamlit
# ==============================
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(coro)
    loop.close()
    return result

# ==============================
# Button
# ==============================
if st.button("🚀 START SEARCH"):
    if not st.session_state.hotels:
        st.warning("Add at least one hotel")
    else:
        results = []
        with st.spinner("Searching Booking.com (USA | USD)..."):
            for h in st.session_state.hotels:
                r = run_async(
                    buscar_booking(
                        h["nome"],
                        h["ini"],
                        h["fim"]
                    )
                )
                results.append(r)

        st.success("Search completed")

        st.dataframe(
            pd.DataFrame(results),
            use_container_width=True
        )
