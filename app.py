import streamlit as st
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import time
import re
import subprocess
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Scanner de Voo Específico", page_icon="✈️", layout="centered")

# --- INSTALAÇÃO AUTOMÁTICA ---
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800} # Resolução um pouco maior
        )
        self.page = self.context.new_page()

    def close(self):
        if self.browser:
            self.browser.close()

    def check_specific_flight(self, origin, dest, date, flight_num, cabin, trip_type_str, max_pax, status_log):
        screenshot_bytes = None
        try:
            self.start_browser()
            
            # Formata a classe
            cabin_map = {
                "Econômica": "economy",
                "Econômica Premium": "premium+economy",
                "Executiva": "business",
                "Primeira Classe": "first"
            }
            cabin_query = cabin_map.get(cabin, "economy")
            
            # --- CORREÇÃO PRINCIPAL: Adiciona 'one way' se necessário ---
            trip_mod = "one way" if trip_type_str == "Só Ida" else "round trip"

            # Monta a URL de busca em linguagem natural
            # Ex: "Flights from GRU to JFK on 2026-01-17 one way first class"
            search_query = f"Flights from {origin} to {dest} on {date} {trip_mod} {cabin_query} class"
            encoded_query = search_query.replace(" ", "+")
            url = f"https://www.google.com/travel/flights?q={encoded_query}"
            
            status_log.write(f"🌍 Acessando busca: {origin} ➔ {dest} ({trip_type_str})")
            self.page.goto(url, timeout=60000)
            
            # Fecha cookies/popups
            try:
                self.page.get_by_role("button", name=re.compile(r"Reject|Rejeitar|Accept|Aceitar|Concordo", re.I)).first.click(timeout=4000)
            except:
                pass

            self.page.wait_for_load_state("networkidle")
            
            # --- LÓGICA DE REGEX DO VOO ---
            # Remove espaços do input (ex: " AA 954 ") -> "AA954"
            clean_flight_num = flight_num.replace(" ", "").strip()
            # Separa letras e números para criar regex flexível (ex: "AA" e "954")
            letters = "".join(re.findall(r"[a-zA-Z]+", clean_flight_num))
            numbers = "".join(re.findall(r"\d+", clean_flight_num))
            # Regex aceita: "AA954", "AA 954", "AA  954"
            regex_pattern = f"{letters}\\s*{numbers}"
            
            status_log.write(f"🔎 Procurando voo **{letters} {numbers}** na lista...")
            
            # Tenta encontrar o card do voo
            # Procura em listitems (estrutura padrão) e também divs genéricas que contenham o texto
            flight_locator = self.page.locator("li, div[role='listitem']").filter(has_text=re.compile(regex_pattern, re.I)).first
            
            if not flight_locator.is_visible():
                # --- CAPTURA DE TELA EM CASO DE ERRO ---
                screenshot_bytes = self.page.screenshot(full_page=False)
                return 0, f"Voo {flight_num} não encontrado na página.", url, screenshot_bytes

            confirmed_seats = 1
            
            # Loop de teste de assentos
            for n in range(2, max_pax + 1):
                status_log.write(f"🔢 Testando **{n}** passageiros...")
                
                # Clica no seletor de passageiros
                btn_pax = self.page.locator("div[jsaction*='click']").filter(has_text=re.compile(r"^\d+$|passenger|passageiro", re.I)).first
                # Fallback
                if not btn_pax.is_visible():
                     btn_pax = self.page.get_by_role("button", name=re.compile(r"passenger|passageiro", re.I)).first
                
                btn_pax.click()
                
                # Adiciona adulto
                btn_add = self.page.locator("button[aria-label*='Add'], button[aria-label*='Adicionar']").first
                btn_add.click()
                
                # Conclui
                btn_done = self.page.get_by_role("button", name=re.compile(r"Done|Concluído|Ok", re.I)).first
                btn_done.click()
                
                # Aguarda atualização
                time.sleep(1.5) 
                self.page.wait_for_load_state("domcontentloaded")
                
                # Verifica se o voo ESPECÍFICO continua lá
                flight_locator = self.page.locator("li, div[role='listitem']").filter(has_text=re.compile(regex_pattern, re.I)).first
                
                if flight_locator.is_visible():
                    confirmed_seats = n
                else:
                    status_log.warning(f"🚫 Voo sumiu com {n} passageiros.")
                    return confirmed_seats, "Limite atingido", url, None
            
            return confirmed_seats, "Capacidade máxima verificada", url, None

        except PlaywrightTimeout:
            # Tenta tirar print mesmo no timeout
            try: screenshot_bytes = self.page.screenshot()
            except: pass
            return -1, "Tempo esgotado (Timeout).", "", screenshot_bytes
        except Exception as e:
            return -1, f"Erro: {str(e)}", "", None
        finally:
            self.close()

# --- INTERFACE ---
st.title("✈️ Scanner de Capacidade de Voo")
st.markdown("Verifique disponibilidade real de assentos.")

install_playwright()

with st.form("flight_form"):
    col1, col2 = st.columns(2)
    with col1:
        origin = st.text_input("Origem (IATA)", "EZE", max_chars=3).upper()
        flight_num = st.text_input("Número do Voo", "AA 954", help="Ex: TP104, AA954")
        cabin_class = st.selectbox("Classe", ["Econômica", "Econômica Premium", "Executiva", "Primeira Classe"], index=3)
    
    with col2:
        dest = st.text_input("Destino (IATA)", "JFK", max_chars=3).upper()
        date_input = st.date_input("Data da Viagem", min_value=datetime.today())
        # NOVA OPÇÃO AQUI
        trip_type = st.radio("Tipo de Viagem", ["Só Ida", "Ida e Volta"], horizontal=True)

    max_pax = st.slider("Testar até quantos passageiros?", 1, 9, 9)
    submitted = st.form_submit_button("🚀 Verificar Disponibilidade", use_container_width=True)

if submitted:
    if not origin or not dest or not flight_num:
        st.error("Preencha todos os campos obrigatórios.")
    else:
        date_str = date_input.strftime("%Y-%m-%d")
        scanner = FlightScanner()
        
        with st.status("Iniciando varredura...", expanded=True) as status:
            seats, msg, final_url, err_img = scanner.check_specific_flight(
                origin, dest, date_str, flight_num, cabin_class, trip_type, max_pax, status
            )
            
            if seats > 0:
                status.update(label="Varredura concluída", state="complete", expanded=False)
            else:
                status.update(label="Voo não encontrado", state="error")
        
        st.divider()
        
        if seats <= 0:
            st.error(msg)
            if final_url:
                st.markdown(f"👉 [Clique para ver a busca original no Google]({final_url})")
            # MOSTRA O PRINT SE HOUVER ERRO
            if err_img:
                st.warning("O que o robô viu na tela:")
                st.image(err_img, caption="Captura de tela do erro", use_container_width=True)
                
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Voo", flight_num)
            c2.metric("Classe", cabin_class)
            color = "normal" if seats >= max_pax else "off"
            c3.metric("Assentos Disponíveis", f"{seats}", delta=msg, delta_color=color)
            
            if seats < max_pax:
                st.info(f"💡 O voo desaparece dos resultados ao buscar {seats + 1} passageiros.")
            else:
                st.success(f"✅ O voo suporta pelo menos {seats} passageiros nesta classe.")
