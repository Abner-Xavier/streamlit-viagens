import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time

st.set_page_config(page_title="Validador Selenium", page_icon="✈️")

# Configuração do Chrome para rodar no Servidor (Nuvem)
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

st.title("🔍 Validador via Selenium (Web Scraping)")
st.markdown("Busca direta no site FlightRadar24.")

flight_input = st.text_input("Digite o número do voo (Ex: AA954):", "").upper().strip()

if st.button("Buscar via Selenium"):
    if flight_input:
        with st.spinner(f"Abrindo navegador virtual e buscando {flight_input}..."):
            driver = get_driver()
            try:
                # Acessa a página direta do voo
                url = f"https://www.flightradar24.com/data/flights/{flight_input}"
                driver.get(url)
                
                # Aguarda o carregamento do elemento que contém a aeronave
                # Nota: Seletores de scraping podem mudar se o site atualizar
                wait = WebDriverWait(driver, 15)
                
                # Tenta localizar o modelo da aeronave na tabela de voos recentes
                # O seletor abaixo busca o texto da primeira linha da tabela de histórico
                aircraft_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "span.srt-12")))
                
                model_text = aircraft_element.text
                
                if model_text:
                    st.success(f"Dados encontrados para {flight_input}!")
                    st.metric("Aeronave Detectada", model_text)
                    
                    if "777" in model_text:
                        st.info("Configuração Boeing 777 detectada: Foco em 6 assentos na Executiva.")
                else:
                    st.warning("Não foi possível extrair o modelo exato. O voo pode estar sem dados recentes.")

            except Exception as e:
                st.error(f"Erro no Scraping: O site pode ter bloqueado o acesso ou mudado o layout.")
                st.caption(f"Detalhe técnico: {e}")
            finally:
                driver.quit()
    else:
        st.warning("Insira um número de voo.")
