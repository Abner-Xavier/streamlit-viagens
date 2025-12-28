import streamlit as st
import asyncio
from playwright.async_api import async_playwright
import os
from datetime import datetime, timedelta

# --- CONFIGURAÇÃO DE AMBIENTE ---
def install_playwright():
    st.info("Instalando navegadores... Aguarde.")
    os.system("playwright install chromium")
    st.success("Navegador instalado!")

# --- FUNÇÃO DE BUSCA NO BOOKING ---
async def buscar_booking(hotel_nome, checkin, checkout):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) # Headless=True para Streamlit Cloud
        
        # User agent para parecer um navegador real
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Montando a URL de busca do Booking com os parâmetros de data
        # ss = nome do hotel, checkin e checkout formatados
        url = (
            f"https://www.booking.com/searchresults.pt-br.html?"
            f"ss={hotel_nome.replace(' ', '+')}&"
            f"checkin={checkin}&"
            f"checkout={checkout}&"
            f"group_adults=2&no_rooms=1&group_children=0"
        )

        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Espera carregar os cards de hotéis
            # O seletor [data-testid="property-card"] é o padrão atual do Booking
            await page.wait_for_selector('[data-testid="property-card"]', timeout=10000)

            # Pegar informações do primeiro resultado (que deve ser o hotel pesquisado)
            primeiro_hotel = page.locator('[data-testid="property-card"]').first()
            
            nome_encontrado = await primeiro_hotel.locator('[data-testid="title"]').inner_text()
            preco = await primeiro_hotel.locator('[data-testid="price-and-discounted-price"]').inner_text()
            
            return {
                "status": "sucesso",
                "hotel": nome_encontrado,
                "preco": preco,
                "url": url
            }

        except Exception as e:
            return {"status": "erro", "mensagem": f"Não foi possível encontrar o preço. O site pode ter bloqueado o acesso ou o hotel não está disponível nestas datas."}
        finally:
            await browser.close()

# --- INTERFACE STREAMLIT ---
def main():
    st.set_page_config(page_title="Buscador Booking", page_icon="🏨")
    st.title("🏨 Pesquisar Hotel no Booking")

    # Sidebar para configuração
    if st.sidebar.button("Configurar Navegador (Rodar apenas 1x)"):
        install_playwright()

    # Entradas do usuário
    hotel_nome = st.text_input("Nome do Hotel:", placeholder="Ex: Copacabana Palace")
    
    col1, col2 = st.columns(2)
    with col1:
        data_in = st.date_input("Check-in", datetime.now() + timedelta(days=7))
    with col2:
        data_out = st.date_input("Check-out", data_in + timedelta(days=2))

    if st.button("Verificar Preço"):
        if hotel_nome:
            # Formata as datas para o padrão do Booking: AAAA-MM-DD
            checkin_str = data_in.strftime("%Y-%m-%d")
            checkout_str = data_out.strftime("%Y-%m-%d")

            with st.spinner(f"Buscando {hotel_nome}..."):
                resultado = asyncio.run(buscar_booking(hotel_nome, checkin_str, checkout_str))
                
                if resultado["status"] == "sucesso":
                    st.success(f"### {resultado['hotel']}")
                    st.metric("Preço Total", resultado["preco"])
                    st.link_button("Ver no Booking", resultado["url"])
                else:
                    st.error(resultado["mensagem"])
        else:
            st.warning("Por favor, digite o nome do hotel.")

if __name__ == "__main__":
    main()
