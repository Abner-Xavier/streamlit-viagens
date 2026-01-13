import streamlit as st
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import subprocess
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Scanner de Voos em Lote", page_icon="✈️", layout="wide")

# --- INSTALAÇÃO ---
def install_playwright():
    if 'playwright_installed' not in st.session_state:
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True)
            st.session_state['playwright_installed'] = True
        except Exception:
            pass

# --- FUNÇÃO DE PARSING (EXTRAIR DADOS DO TEXTO) ---
def parse_flight_text(text_input, year):
    flights = []
    # Regex para capturar: (ORIGEM)-(DESTINO) ... (CIA NUMERO) ... (MES DIA)
    # Ex: EZE-JFK ... AA 954 ... Jan 17
    regex_pattern = r"([A-Z]{3})-([A-Z]{3}).*?([A-Z0-9]{2}\s?\d{1,4}).*?([A-Za-z]{3}\s\d{1,2})"
    
    lines = text_input.strip().split('\n')
    
    for line in lines:
        match = re.search(regex_pattern, line)
        if match:
            origin, dest, flight_num, date_part = match.groups()
            
            # Converter data textual (Jan 17) para YYYY-MM-DD
            try:
                date_obj = datetime.strptime(f"{date_part} {year}", "%b %d %Y")
                date_formatted = date_obj.strftime("%Y-%m-%d")
                
                flights.append({
                    "Origem": origin,
                    "Destino": dest,
                    "Voo": flight_num.strip(),
                    "Data": date_formatted,
                    "Texto Original": line
                })
            except ValueError:
                continue
                
    return pd.DataFrame(flights)

# --- CLASSE DO SCANNER ---
class BatchScanner:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None

    def start(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        self.page = self.context.new_page()

    def stop(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def check_flight(self, row, cabin_class, max_pax, one_way):
        try:
            origin = row['Origem']
            dest = row['Destino']
            date = row['Data']
            flight_num = row['Voo']
            
            # Mapeamento de classe
            cabin_map = {"Econômica": "economy", "Executiva": "business", "Primeira": "first"}
            cabin_query = cabin_map.get(cabin_class, "economy")
            trip_type = "one way" if one_way else "round trip"

            # URL
            query = f"Flights from {origin} to {dest} on {date} {trip_type} {cabin_query} class"
            url = f"https://www.google.com/travel/flights?q={query.replace(' ', '+')}"
            
            self.page.goto(url, timeout=45000)
            
            # Tenta fechar cookies
            try:
                self.page.get_by_role("button", name=re.compile(r"Reject|Rejeitar|Accept|Aceitar", re.I)).first.click(timeout=3000)
            except:
                pass
            
            self.page.wait_for_load_state("networkidle")

            # Regex para achar o voo na página
            clean_num = flight_num.replace(" ", "")
            letters = "".join(re.findall(r"[a-zA-Z]+", clean_num))
            numbers = "".join(re.findall(r"\d+", clean_num))
            flight_regex = re.compile(f"{letters}\\s*{numbers}", re.I)

            # Verifica se voo existe
            if not self.page.locator("li, div[role='listitem']").filter(has_text=flight_regex).first.is_visible():
                return 0, "Voo não encontrado"

            confirmed = 1
            
            # Loop de disponibilidade
            for n in range(2, max_pax + 1):
                # Abre Pax
                btn_pax = self.page.locator("div[jsaction*='click']").filter(has_text=re.compile(r"^\d+$|passenger", re.I)).first
                if not btn_pax.is_visible(): break
                btn_pax.click()
                
                # Add Adult
                self.page.locator("button[aria-label*='Add'], button[aria-label*='Adicionar']").first.click()
                
                # Done
                self.page.get_by_role("button", name=re.compile(r"Done|Concluído", re.I)).first.click()
                
                # Wait
                time.sleep(1)
                self.page.wait_for_load_state("domcontentloaded")
                
                # Check Visibility
                if self.page.locator("li, div[role='listitem']").filter(has_text=flight_regex).first.is_visible():
                    confirmed = n
                else:
                    return confirmed, "Limite atingido"
            
            return confirmed, "Capacidade máxima"

        except Exception as e:
            return -1, f"Erro: {str(e)}"

# --- INTERFACE ---
st.title("✈️ Scanner de Voos em Lote")
st.markdown("Cole sua lista de voos abaixo para verificar a disponibilidade de todos de uma vez.")

install_playwright()

col1, col2 = st.columns([2, 1])

with col1:
    raw_text = st.text_area(
        "Cole a lista de voos aqui:", 
        height=200,
        placeholder="Seat Counts EZE-JFK Dep 8:45PM AA 954 – Jan 17\nSeat Counts GRU-MIA Dep 11:30PM AA 930 – Jan 17",
        help="O sistema detecta automaticamente o formato Origem-Destino, Voo e Data."
    )

with col2:
    target_year = st.number_input("Ano da Viagem", min_value=2024, max_value=2030, value=2026)
    cabin = st.selectbox("Classe", ["Econômica", "Executiva", "Primeira"])
    max_pax = st.slider("Max Passageiros", 1, 9, 9)
    is_one_way = st.checkbox("Apenas Ida (One Way)", value=True)

# Parse e Preview
if raw_text:
    df_flights = parse_flight_text(raw_text, target_year)
    
    if not df_flights.empty:
        st.info(f"{len(df_flights)} voos detectados.")
        st.dataframe(df_flights[["Origem", "Destino", "Voo", "Data"]], use_container_width=True)
        
        if st.button("🚀 Iniciar Scanner em Lote", type="primary"):
            scanner = BatchScanner()
            results = []
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                scanner.start()
                total = len(df_flights)
                
                for index, row in df_flights.iterrows():
                    status_text.write(f"⏳ Processando {index+1}/{total}: **{row['Voo']}** ({row['Origem']}-{row['Destino']})...")
                    
                    seats, msg = scanner.check_flight(row, cabin, max_pax, is_one_way)
                    
                    results.append({
                        "Voo": row['Voo'],
                        "Rota": f"{row['Origem']}-{row['Destino']}",
                        "Data": row['Data'],
                        "Assentos": seats,
                        "Status": msg
                    })
                    
                    progress_bar.progress((index + 1) / total)
                
                scanner.stop()
                status_text.success("Processamento concluído!")
                
                # Exibe Resultados Finais
                df_results = pd.DataFrame(results)
                
                # Formatação condicional (destaca voos com assentos > 0)
                st.subheader("📊 Resultados de Disponibilidade")
                st.dataframe(
                    df_results.style.map(lambda x: 'color: red' if x == 0 or x == -1 else 'color: green', subset=['Assentos']),
                    use_container_width=True
                )
                
            except Exception as e:
                st.error(f"Erro crítico: {e}")
                scanner.stop()
    else:
        st.warning("Nenhum voo identificado no texto. Verifique se o formato está correto (Ex: EZE-JFK ... AA 123 ... Jan 01)")
