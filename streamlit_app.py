import streamlit as st
import asyncio
import re
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# -------------------------------
# CONFIG STREAMLIT
# -------------------------------
st.set_page_config(
    page_title="Booking Search Bot",
    layout="wide"
)

st.title("🏨 Automação Booking — Pesquisa por Nome")

# -------------------------------
# FUNÇÕES AUXILIARES
# -------------------------------
def gerar_pernoites(data_ini, data_fim):
    periodos = []
    atual = data_ini
    while atual < data_fim:
        prox = atual + timedelta(days=1)
        periodos.append((atual.strftime("%Y-%m-%d"), prox.strftime("%Y-%m-%d")))
        atual = prox
    return periodos


async def coletar_dados(page, hotel_nome, checkin, checkout):
    resultados = []

    query = hotel_nome.replace(" ", "+")
    url = (
        f"https://www.booking.com/searchresults.pt-br.html"
        f"?ss={query}&checkin={checkin}&checkout={checkout}&selected_currency=USD"
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
        await stealth_async(hotel_page)

        await hotel_page.goto("https://www.booking.com" + href, timeout=60000)
        await hotel_page.wait_for_load_state("domcontentloaded")
        await hotel_page.wait_for_timeout(3000)

        rows = await hotel_page.query_selector_all(
            "table.hprt-table tbody tr.hprt-table-row"
        )

        quarto_atual = "Desconhecido"
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
                    valor = valor.replace(".", "").replace(",", ".")
                    preco = float(valor)

                    resultados.append({
                        "Hotel": hotel_nome,
                        "Check-in": checkin,
                        "Check-out": checkout,
                        "Quarto": quarto_atual,
                        "Área (m²)": area_atual,
                        "Preço (USD)": round(preco, 2)
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
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1280, "height": 800}
        )

        progresso = st.progress(0.0)
        status = st.empty()

        for i, hotel in enumerate(hoteis):
            page = await context.new_page()
            await stealth_async(page)

            periodos = gerar_pernoites(hotel["ini"], hotel["fim"])

            for c_in, c_out in periodos:
                status.info(f"🔎 {hotel['nome']} | {c_in}")
                dados = await coletar_dados(page, hotel["nome"], c_in, c_out)
                dados_finais.extend(dados)

            await page.close()
            progresso.progress((i + 1) / len(hoteis))

        await browser.close()

    return dados_finais


# -------------------------------
# SESSION STATE
# -------------------------------
if "fila_hoteis" not in st.session_state:
    st.session_state.fila_hoteis = []


# -------------------------------
# SIDEBAR
# -------------------------------
with st.sidebar:
    st.header("Configurações")

    nome = st.text_input("Nome do Hotel")
    col1, col2 = st.columns(2)

    d_ini = col1.date_input("Check-in", datetime(2025, 12, 27))
    d_fim = col2.date_input("Check-out", datetime(2025, 12, 30))

    if st.button("➕ Adicionar Hotel"):
        if nome:
            st.session_state.fila_hoteis.append({
                "nome": nome,
                "ini": d_ini,
                "fim": d_fim
            })
            st.rerun()

    if st.button("🗑️ Limpar Lista"):
        st.session_state.fila_hoteis = []
        st.rerun()


# -------------------------------
# EXECUÇÃO
# -------------------------------
if st.session_state.fila_hoteis:
    st.subheader("📋 Hotéis na fila")
    st.dataframe(pd.DataFrame(st.session_state.fila_hoteis), use_container_width=True)

    if st.button("🚀 INICIAR PESQUISA"):
        with st.spinner("Buscando dados no Booking..."):
            resultado = asyncio.run(
                rodar_scrapers(st.session_state.fila_hoteis)
            )

        if resultado:
            df = pd.DataFrame(resultado)
            st.success("✅ Pesquisa finalizada")
            st.dataframe(df, use_container_width=True)
            st.download_button(
                "⬇️ Baixar CSV",
                df.to_csv(index=False),
                file_name="booking_resultados.csv",
                mime="text/csv"
            )
        else:
            st.warning("Nenhum dado encontrado.")
else:
    st.info("Adicione hotéis na barra lateral para iniciar.")
