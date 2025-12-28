import streamlit as st
import asyncio
from playwright.async_api import async_playwright
import os
from datetime import datetime, timedelta

# --- CONFIGURAÇÃO DE AMBIENTE ---
def install_playwright():
    st.info("Instalando navegadores... Isso pode levar 1-2 minutos.")
    os.system("playwright install chromium")

# --- FUNÇÃO DE BUSCA ---
async def buscar_booking(hotel_nome, checkin, checkout):
    async with async_playwright() as p:
        # Lançamos o navegador com argumentos para evitar detecção básica
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        # URL montada para busca direta
        url = (
            f"https://www.booking.com/searchresults.pt-br.html?"
            f"ss={hotel_nome.replace(' ', '+')}&"
            f"checkin={checkin}&"
            f"checkout={checkout}&"
            f"group_adults=2&no_rooms=1&group_children=0&selected_currency=BRL"
        )

        try:
            await page.goto(url, wait_until="load", timeout=60000)
            await asyncio.sleep(5) # Espera o carregamento dinâmico

            # 1. Tentar fechar banner de cookies ou login se aparecer
            try:
                await page.click("button[aria-label='Ignorar informações de login']", timeout=3000)
            except: pass

            # 2. Tentar encontrar o card do hotel (usando múltiplos seletores)
            # O Booking vive mudando esses nomes
            seletores_card = [
                '[data-testid="property-card"]', 
                '.sr_property_block', 
                '[data-block-id="hotel_list"]'
            ]
            
            card_encontrado = None
            for sel in seletores_card:
                if await page.query_selector(sel):
                    card_encontrado = page.locator(sel).first
                    break

            if card_encontrado:
                nome = await card_encontrado.locator('[data-testid="title"]').inner_text()
                # Tenta pegar o preço (pode variar o seletor)
                try:
                    preco = await card_encontrado.locator('[data-testid="price-and-discounted-price"]').inner_text()
                except:
                    preco = "Preço sob consulta"
                
                return {"status": "sucesso", "hotel": nome, "preco": preco, "url": url}
            
            # Se não achar nada, tira print para debug
            await page.screenshot(path="erro_debug.png")
            return {"status": "erro", "mensagem": "Hotel não localizado. Veja o print abaixo.", "debug": True}

        except Exception as e:
            await page.screenshot(path="erro_debug.png")
            return {"status": "erro", "mensagem": f"Erro técnico: {str(e)}", "debug": True}
        finally:
            await browser.close()

# --- INTERFACE ---
def main():
    st.set_page_config(page_title="Buscador Booking", page_icon="🏨")
    st.title("🏨 Pesquisar Hotel no Booking")

    if st.sidebar.button("Configurar Navegador"):
        install_playwright()

    hotel_nome = st.text_input("Nome do Hotel:", "Hilton sao paulo Morumbi")
    
    col1, col2 = st.columns(2)
    with col1:
        data_in = st.date_input("Check-in", datetime.now() + timedelta(days=10))
    with col2:
        data_out = st.date_input("Check-out", data_in + timedelta(days=2))

    if st.button("Verificar Preço"):
        with st.spinner("Consultando Booking..."):
            res = asyncio.run(buscar_booking(hotel_nome, data_in.strftime("%Y-%m-%d"), data_out.strftime("%Y-%m-%d")))
            
            if res["status"] == "sucesso":
                st.balloons()
                st.success(f"**Hotel:** {res['hotel']}")
                st.subheader(f"Valor: {res['preco']}")
                st.link_button("Ir para o site", res["url"])
            else:
                st.error(res["mensagem"])
                if "debug" in res and os.path.exists("erro_debug.png"):
                    st.image("erro_debug.png", caption="O que o robô viu no momento do erro")

if __name__ == "__main__":
    main()
