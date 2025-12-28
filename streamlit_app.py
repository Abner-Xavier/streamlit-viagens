import streamlit as st
import asyncio
from datetime import date
from playwright.async_api import async_playwright
import pandas as pd
from urllib.parse import quote_plus

# ==============================
# Streamlit config
# ==============================
st.set_page_config(
    page_title="Booking Automation — USA | USD",
    layout="wide"
)

st.title("🏨 Booking Automation — USA | USD")

# ==============================
# Sidebar UI
# ==============================
with st.sidebar:
    st.header("Search settings")

    mode = st.radio(
        "Search mode",
        ["Search by hotel name", "Use Booking hotel URL"]
    )

    hotel_name = st.text_input(
        "Hotel name",
        value="Hilton Sao Paulo Morumbi",
        disabled=(mode == "Use Booking hotel URL")
    )

    hotel_url = st.text_input(
        "Booking hotel URL",
        placeholder="https://www.booking.com/hotel/...",
        disabled=(mode == "Search by hotel name")
    )

    col1, col2 = st.columns(2)
    with col1:
        checkin = st.date_input("Check-in", value=date(2025, 12, 30))
    with col2:
        checkout = st.date_input("Check-out", value=date(2026, 1, 3))

    add = st.button("➕ Add hotel")
    clear = st.button("🗑 Clear list")

# ==============================
# Session state
# ==============================
if "hotels" not in st.session_state:
    st.session_state.hotels = []

if add:
    st.session_state.hotels.append({
        "mode": mode,
        "name": hotel_name,
        "url": hotel_url,
        "checkin": str(checkin),
        "checkout": str(checkout)
    })

if clear:
    st.session_state.hotels = []

# ==============================
# Display queued hotels
# ==============================
st.subheader("📋 Hotels queued")

if st.session_state.hotels:
    st.dataframe(pd.DataFrame(st.session_state.hotels), use_container_width=True)
else:
    st.info("No hotels added")

# ==============================
# URL builder
# ==============================
def build_booking_url(h):
    if h["mode"] == "Use Booking hotel URL":
        return (
            f"{h['url']}?"
            f"checkin={h['checkin']}&checkout={h['checkout']}"
            "&group_adults=2&no_rooms=1"
            "&selected_currency=USD&lang=en-us"
        )
    else:
        return (
            "https://www.booking.com/searchresults.html"
            f"?ss={quote_plus(h['name'])}"
            f"&checkin_year={h['checkin'][:4]}"
            f"&checkin_month={h['checkin'][5:7]}"
            f"&checkin_monthday={h['checkin'][8:10]}"
            f"&checkout_year={h['checkout'][:4]}"
            f"&checkout_month={h['checkout'][5:7]}"
            f"&checkout_monthday={h['checkout'][8:10]}"
            "&group_adults=2&group_children=0&no_rooms=1"
            "&selected_currency=USD&lang=en-us"
        )

# ==============================
# Playwright scraper (SAFE)
# ==============================
async def scrape_hotels(hotels):
    results = []

    async with async_playwright() as p:
     browser = await p.chromium.launch(
    headless=True,
    args=["--no-sandbox", "--disable-dev-shm-usage"]
)

        context = await browser.new_context(
            locale="en-US",
            timezone_id="America/New_York"
        )

        page = await context.new_page()

        for h in hotels:
            url = build_booking_url(h)

            await page.goto(url, timeout=90000)
            await page.wait_for_timeout(5000)

            cards = await page.locator('[data-testid="property-card"]').count()

            results.append({
                "Hotel": h["name"] if h["name"] else h["url"],
                "Check-in": h["checkin"],
                "Check-out": h["checkout"],
                "Results found": cards,
                "Currency": "USD",
                "Region": "USA"
            })

        await browser.close()

    return results

# ==============================
# Async runner (Streamlit-safe)
# ==============================
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(coro)
    loop.close()
    return result

# ==============================
# Start search
# ==============================
if st.button("🚀 START SEARCH"):
    if not st.session_state.hotels:
        st.warning("Add at least one hotel")
    else:
        with st.spinner("Searching Booking.com..."):
            results = run_async(scrape_hotels(st.session_state.hotels))

        st.success("Search completed")
        st.dataframe(pd.DataFrame(results), use_container_width=True)
