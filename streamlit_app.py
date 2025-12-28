import streamlit as st
import asyncio
import re
import os
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
import playwright_stealth

# --- CONFIGURAÇÃO DE AMBIENTE ---
def install_browsers():
    if not os.path.exists("/home/runner/.cache/ms-playwright"):
        with st.spinner("Configurando navegadores no servidor..."):
            os.system("playwright install chromium")

# --- LÓGICA DO AGENTE (BACK-END) ---
async def extrair_suites_agente(url_base, checkin, checkout):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        
        # CORREÇÃO DO ERRO DE TYPEERROR/STEALTH
        try:
            # Tenta a versão assíncrona se disponível
            await playwright_stealth.stealth_async(page)
        except (AttributeError, TypeError):
            # Fallback para a versão padrão (que funciona em muitos ambientes async)
            from playwright_stealth import stealth
            await stealth(page)

        # Montagem da URL detalhada
        url = f"{url_base}?checkin={checkin}&checkout={checkout}&group_adults=2&no_rooms=1&selected_currency=USD&lang=en-us"
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Fechar pop-ups bloqueadores
            try:
                await page.click("button[aria-label*='Close'], button:has-text('Dismiss')", timeout=5000)
            except: pass

            # Esperar carregar a tabela de quartos
            await page.wait_for_selector(".hprt-roomtype-link", timeout=20000)
            
            rows = await page.query_selector_all("table.hprt-table tbody tr.hprt-table-row")
            dados = []
            
            # Lógica de propagação de nome/área para linhas sem essas infos
            last_room = "Desconhecido"
            last_area = 0

            for row in rows:
                room_el = await row.query_selector(".hprt-roomtype-link")
                if room_el:
                    last_room = (await room_el.inner_text()).strip()
                    # Captura m2 do texto da linha
                    row_text = await row.inner_text()
                    area_match = re.search(r"(\d+)\s*(?:m²|sq m)", row_text)
                    last_area = int(area_match.group(1)) if area_match else 0

                price_el = await row.query_selector(".bui-price-display__value")
                if price_el:
                    price_txt = await price_el.inner_text()
                    price_val = re.search(r"([\d,.]+)", price_txt.replace("USD", ""))
                    price = float(price_val.group(1).replace(",", "")) if price_val else 0
                    
                    dados.append({
                        "Suíte": last_room,
                        "Área_m2": last_area,
                        "Preço_USD": price
                    })

            await browser.close()
            return dados
        except Exception as e:
            st.error(f"Erro na coleta: {e}")
            await browser.close()
            return []

# --- INTERFACE PARA A EQUIPE (FRONT-END) ---
st.set_page_config(page_title="Agente de Suítes", layout="wide")
st.title("🏨 Agente de Inventário e Suite Count")
st.write("Automatize a tarefa de 45 minutos da sua equipe.")



with st.sidebar:
    st.header("Entrada de Dados")
    url_input = st.text_input("URL do Hotel (Booking)")
    c1, c2 = st.columns(2)
    with c1:
        d_in = st.date_input("Check-in", datetime.now() + timedelta(days=7))
    with c2:
        d_out = st.date_input("Check-out", d_in + timedelta(days=1))

if st.button("🚀 Executar Agente"):
    if not url_input:
        st.warning("Insira uma URL válida.")
    else:
        install_browsers()
        with st.spinner("O Agente está processando a tabela de quartos..."):
            # Rodar o loop assíncrono de forma segura dentro do Streamlit
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            resultados = loop.run_until_complete(extrair_suites_agente(url_input, str(d_in), str(d_out)))
            
            if resultados:
                df = pd.DataFrame(resultados)
                
                # --- O GRANDE GANHO DE TEMPO: RESUMO ---
                st.subheader("📊 Resumo para Relatório (Suite Count)")
                resumo = df.groupby(['Suíte', 'Área_m2']).size().reset_index(name='Quantidade')
                st.table(resumo)
                
                st.subheader("📋 Dados Detalhados")
                st.dataframe(df)
                
                # Botão de download
                csv = df.to_csv(index=False, sep=";").encode('utf-8-sig')
                st.download_button("📥 Baixar CSV para Equipe", csv, "inventario.csv", "text/csv")
            else:
                st.error("Nenhum dado encontrado. Verifique a URL ou disponibilidade.")
