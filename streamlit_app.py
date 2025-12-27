import os
import streamlit as st
import asyncio
import re
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
# IMPORTANTE: Importamos a FUNÇÃO stealth, não o módulo inteiro
from playwright_stealth import stealth 

def preparar_navegador():
    if 'navegador_pronto' not in st.session_state:
        with st.spinner("Configurando Chromium..."):
            os.system("playwright install chromium")
            st.session_state.navegador_pronto = True

def gerar_periodos(data_ini, data_fim):
    periodos = []
    atual = data_ini
    while atual < data_fim:
        proximo = atual + timedelta(days=1)
        periodos.append((atual.strftime("%Y-%m-%d"), proximo.strftime("%Y-%m-%d")))
        atual = proximo
    return periodos

async def extrair_dados(page, hotel_nome, checkin, checkout):
    query = hotel_nome.replace(" ", "+")
    url = f"https://www.booking.com/searchresults.pt-br.html?ss={query}&checkin={checkin}&checkout={checkout}&selected_currency=USD"
    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        primeiro = await page.query_selector("div[data-testid='property-card']")
        if primeiro:
            async with page.expect_popup() as popup_info:
                await primeiro.query_selector("a[data-testid='title-link']").click()
            h_page = await popup_info.value
            await h_page.wait_for_load_state("domcontentloaded")
            rows = await h_page.query_selector_all("table.hprt-table tbody tr.hprt-table-row")
            res = []
            q, a = "Desconhecido", None
            for r in rows:
                n_el = await r.query_selector(".hprt-roomtype-link")
                if n_el:
                    q = (await n_el.inner_text()).strip()
                    txt = await r.inner_text()
                    m2 = re.search(r"(\d+)\s*(?:m²|sq m)", txt)
                    a = int(m2.group(1)) if m2 else None
                p_el = await r.query_selector("span[data-testid='price-and-discounted-price'], .bui-price-display__value")
                if p_el:
                    v_txt = await p_el.inner_text()
                    v_num = re.search(r"[\d,.]+", v_txt)
                    if v_num:
                        valor = float(v_num.group().replace(",", ""))
                        res.append({
                            "Hotel_Name": hotel_nome,
                            "Checkin": checkin,
                            "Checkout": checkout,
                            "Room_Name": q,
                            "Area_m2": a,
                            "Price_USD": f"$ {valor:.2f}"
                        })
            await h_page.close()
            return res
        return []
    except:
        return []

# INTERFACE
st.title("🏨 Automação Booking")
if "hoteis" not in st.session_state: st.session_state.hoteis = []

with st.sidebar:
    nome = st.text_input("Nome do Hotel")
    c1, c2 = st.columns(2)
    d1 = c1.date_input("Início", datetime(2025, 12, 27))
    d2 = c2.date_input("Fim", datetime(2025, 12, 30))
    if st.button("➕ Adicionar"):
        st.session_state.hoteis.append({"nome": nome, "ini": d1, "fim": d2})
    if st.button("🗑️ Limpar"):
        st.session_state.hoteis = []
        st.rerun()

if st.session_state.hoteis:
    st.table(pd.DataFrame(st.session_state.hoteis))
    if st.button("🚀 INICIAR"):
        preparar_navegador()
        async def main():
            resultados = []
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                page = await browser.new_page()
                
                # AQUI É O SEGREDO: chamamos stealth(page)
                # Como importamos 'from playwright_stealth import stealth', não dá erro de módulo!
                await stealth(page) 

                pbar = st.progress(0)
                for i, h in enumerate(st.session_state.hoteis):
                    dias = gerar_periodos(h["ini"], h["fim"])
                    for ci, co in dias:
                        data = await extrair_dados(page, h['nome'], ci, co)
                        resultados.extend(data)
                    pbar.progress((i + 1) / len(st.session_state.hoteis))
                await browser.close()
            return resultados

        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            final = loop.run_until_complete(main())
            loop.close()
            if final:
                st.dataframe(pd.DataFrame(final), use_container_width=True)
            else:
                st.warning("Nenhum dado encontrado.")
        except Exception as e:
            st.error(f"Erro: {e}")
