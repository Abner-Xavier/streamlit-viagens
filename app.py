import streamlit as st
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import time
import re
import subprocess
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Scanner de Voo Específico", page_icon="✈️", layout="centered")

# --- INSTALAÇÃO AUTOMÁTICA (ESSENCIAL PARA STREAMLIT CLOUD) ---
def install_playwright():
    if 'playwright_installed' not in st.session_state:
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True)
            st.session_state['playwright_installed'] = True
        except Exception as e:
            st.error(f"Erro na instalação do navegador: {e}")

# --- CLASSE DO ROBÔ ---
class FlightScanner:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None

    def start_browser(self):
        playwright = sync_playwright().start()
        self.browser = playwright.chromium.launch(
            headless=True, 
            args=["--disable-blink-features=AutomationControlled"]
        )
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.page = self.context.new_page()

    def close(self):
        if self.browser:
            self.browser.close()

    def check_specific_flight(self, origin, dest, date, flight_num, cabin, max_pax, status_log):
        try:
            self.start_browser()
            
            # Formata a classe para a URL do Google
            cabin_map = {
                "Econômica": "economy",
                "Econômica Premium": "premium+economy",
                "Executiva": "business",
                "Primeira Classe": "first"
            }
            cabin_query = cabin_map.get(cabin, "economy")
            
            # Monta a URL de busca inteligente
            # Ex: Flights from GRU to LIS on 2024-10-20 business class
            search_query = f"Flights from {origin} to {dest} on {date} {cabin_query} class"
            encoded_query = search_query.replace(" ", "+")
            url = f"https://www.google.com/travel/flights?q={encoded_query}"
            
            status_log.write(f"🌍 Iniciando busca: {origin} ➔ {dest} ({cabin})")
            self.page.goto(url, timeout=60000)
            
            # Tenta fechar cookies
            try:
                self.page.get_by_role("button", name=re.compile(r"Reject|Rejeitar|Accept|Aceitar|Concordo", re.I)).first.click(timeout=4000)
            except:
                pass

            self.page.wait_for_load_state("networkidle")

            # REGEX para encontrar o voo (ignora espaços, ex: TP104 acha TP 104)
            # Remove espaços do input do usuário para criar a regex
            clean_flight_num = flight_num.replace(" ", "")
            # Regex flexível: Procura letras, espaço opcional, números
            # Ex: se user digita TP104, regex vira /TP\s*104/i
            letters = "".join(re.findall(r"[a-zA-Z]+", clean_flight_num))
            numbers = "".join(re.findall(r"\d+", clean_flight_num))
            regex_pattern = f"{letters}\\s*{numbers}"
            
            status_log.write(f"🔎 Procurando voo **{flight_num}** na lista...")
            
            # Verifica se o voo existe com 1 passageiro
            flight_locator = self.page.locator("li, div[role='listitem']").filter(has_text=re.compile(regex_pattern, re.I)).first
            
            if not flight_locator.is_visible():
                return 0, f"Voo {flight_num} não encontrado nesta data/rota.", url

            confirmed_seats = 1
            
            # Loop para testar assentos
            for n in range(2, max_pax + 1):
                status_log.write(f"🔢 Testando disponibilidade para **{n}** passageiros...")
                
                # 1. Abre menu de passageiros (clica onde tem número)
                btn_pax = self.page.locator("div[jsaction*='click']").filter(has_text=re.compile(r"^\d+$|passenger|passageiro", re.I)).first
                btn_pax.click()
                
                # 2. Adiciona adulto
                btn_add = self.page.locator("button[aria-label*='Add'], button[aria-label*='Adicionar']").first
                btn_add.click()
                
                # 3. Conclui
                btn_done = self.page.get_by_role("button", name=re.compile(r"Done|Concluído|Ok", re.I)).first
                btn_done.click()
                
                # 4. Aguarda reload
                time.sleep(1.5) 
                self.page.wait_for_load_state("domcontentloaded")
                
                # 5. Verifica se o voo ESPECÍFICO ainda está na tela
                # Recriamos o locator pois a página mudou
                flight_locator = self.page.locator("li, div[role='listitem']").filter(has_text=re.compile(regex_pattern, re.I)).first
                
                if flight_locator.is_visible():
                    confirmed_seats = n
                else:
                    status_log.warning(f"🚫 Voo sumiu com {n} passageiros.")
                    return confirmed_seats, "Limite atingido", url
            
            return confirmed_seats, "Capacidade máxima verificada", url

        except PlaywrightTimeout:
            return -1, "Tempo esgotado. Tente novamente.", ""
        except Exception as e:
            return -1, f"Erro: {str(e)}", ""
        finally:
            self.close()

# --- INTERFACE ---
st.title("✈️ Scanner de Capacidade de Voo")
st.markdown("Verifique quantos assentos restam em um voo específico (Econômica, Executiva, etc).")

# Instalação silenciosa
install_playwright()

with st.form("flight_form"):
    col1, col2 = st.columns(2)
    with col1:
        origin = st.text_input("Origem (IATA)", "GRU", max_chars=3, help="Ex: GRU, LIS, JFK").upper()
        flight_num = st.text_input("Número do Voo", "TP 104", help="Ex: TP104, LA8000")
        cabin_class = st.selectbox("Classe", ["Econômica", "Econômica Premium", "Executiva", "Primeira Classe"])
    
    with col2:
        dest = st.text_input("Destino (IATA)", "LIS", max_chars=3).upper()
        date_input = st.date_input("Data da Viagem", min_value=datetime.today())
        max_pax = st.slider("Testar até quantos assentos?", 1, 9, 9)

    submitted = st.form_submit_button("🚀 Verificar Disponibilidade", use_container_width=True)

if submitted:
    if not origin or not dest or not flight_num:
        st.error("Preencha Origem, Destino e Número do Voo.")
    else:
        # Converter data para formato string YYYY-MM-DD
        date_str = date_input.strftime("%Y-%m-%d")
        
        scanner = FlightScanner()
        
        with st.status("Iniciando varredura...", expanded=True) as status:
            seats, msg, final_url = scanner.check_specific_flight(origin, dest, date_str, flight_num, cabin_class, max_pax, status)
            
            if seats > 0:
                status.update(label="Varredura concluída", state="complete", expanded=False)
            else:
                status.update(label="Erro na varredura", state="error")
        
        st.divider()
        
        if seats == -1:
            st.error(msg)
        elif seats == 0:
            st.warning(f"O voo **{flight_num}** não foi encontrado para esta data/rota na classe {cabin_class}.")
            if final_url:
                st.markdown(f"[Ver no Google Flights]({final_url})")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Voo", flight_num)
            c1.caption(f"{origin} ➔ {dest}")
            
            c2.metric("Classe", cabin_class)
            
            color = "normal" if seats >= max_pax else "off"
            c3.metric("Assentos Disponíveis", f"{seats}", delta=msg, delta_color=color)
            
            if seats < max_pax:
                st.info(f"💡 Dica: Há exatamente **{seats}** assentos disponíveis nesta tarifa.")
            else:
                st.success(f"✅ Há **pelo menos {seats}** assentos disponíveis.")
