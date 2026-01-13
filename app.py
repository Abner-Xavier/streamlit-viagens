import streamlit as st
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import subprocess
import io
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Scanner Master - Google Flights", page_icon="✈️", layout="wide")

# --- INSTALAÇÃO ---
def install_playwright():
    if 'playwright_installed' not in st.session_state:
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True)
            st.session_state['playwright_installed'] = True
        except Exception:
            pass

install_playwright()

# --- AUXILIARES ---
def parse_text(text, year):
    flights = []
    # Regex flexível para capturar formato Seat Counts ou texto livre
    # Procura: AA 930 ... GRU-MIA ... Jan 17
    lines = text.strip().split('\n')
    for line in lines:
        try:
            # Tenta extrair número do voo (Letras + Numeros)
            flight_match = re.search(r"([A-Z0-9]{2})\s?(\d{2,4})", line)
            # Tenta extrair rota (AAA-BBB)
            route_match = re.search(r"([A-Z]{3})-([A-Z]{3})", line)
            # Tenta extrair data (Jan 17)
            date_match = re.search(r"([A-Za-z]{3}\s\d{1,2})", line)
            
            if flight_match and route_match and date_match:
                date_obj = datetime.strptime(f"{date_match.group(1)} {year}", "%b %d %Y")
                flights.append({
                    "Voo Completo": f"{flight_match.group(1)} {flight_match.group(2)}", # Ex: AA 930
                    "Numero": flight_match.group(2), # Ex: 930
                    "Cia": flight_match.group(1), # Ex: AA
                    "Origem": route_match.group(1),
                    "Destino": route_match.group(2),
                    "Data": date_obj.date()
                })
        except:
            continue
    return pd.DataFrame(flights)

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Resultados')
    return output.getvalue()

# --- CLASSE DO SCANNER ---
class FlightBot:
    def __init__(self, headless=True):
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        p = sync_playwright().start()
        self.browser = p.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"]
        )
        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 900}, # Tela grande para carregar tudo
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.page = self.context.new_page()

    def stop(self):
        if self.browser: self.browser.close()

    def check_flight(self, row, cabin_class, max_pax, one_way):
        try:
            # 1. Monta URL
            date_str = row['Data'].strftime("%Y-%m-%d")
            trip = "one way" if one_way else "round trip"
            cabin_map = {"Econômica": "economy", "Executiva": "business", "Primeira": "first"}
            
            # URL Genérica da Rota (Busca ampla para garantir que o voo apareça)
            query = f"Flights from {row['Origem']} to {row['Destino']} on {date_str} {trip} {cabin_map[cabin_class]} class"
            url = f"https://www.google.com/travel/flights?q={query.replace(' ', '+')}"
            
            self.page.goto(url, timeout=60000)
            try: self.page.get_by_role("button", name=re.compile(r"Reject|Aceitar", re.I)).first.click(timeout=3000)
            except: pass
            
            self.page.wait_for_load_state("networkidle")
            time.sleep(3) # Tempo para renderizar lista

            # 2. ENCONTRAR O CARTÃO DO VOO (Estratégia Relativa)
            # Pegamos todos os elementos de lista que parecem cartões de voo
            flight_cards = self.page.locator("li, div[role='listitem']").all()
            
            target_card = None
            extracted_info = "N/A"
            
            # Itera sobre todos os voos da tela para achar o AA 930
            for card in flight_cards:
                text = card.inner_text()
                # Verifica se o numero (930) e a Cia (AA) estão no texto desse cartão
                if row['Numero'] in text and row['Cia'] in text:
                    target_card = card
                    # Extrai infos visuais para confirmação
                    try:
                        # Tenta pegar horário/preço usando estrutura genérica
                        times = card.locator("span[aria-label*='Departure'], span[aria-label*='Partida']").first.inner_text() 
                        price = card.locator("div[class*='BVJ']").last.inner_text() # Classes mudam, mas tentar pegar último texto
                        extracted_info = f"Card encontrado. Texto parcial: {text[:50]}..."
                    except:
                        extracted_info = "Card encontrado (dados visuais não extraídos)"
                    break
            
            if not target_card:
                return 0, "Voo não encontrado na lista (Cia/Num não batem)", self.page.screenshot(), "---"

            # 3. TESTAR PASSAGEIROS
            confirmed_seats = 1
            
            for n in range(2, max_pax + 1):
                # Menu Pax (Topo da página)
                btn_pax = self.page.locator("div[jsaction*='click']").filter(has_text=re.compile(r"^\d+$|passenger|passageiro", re.I)).first
                if not btn_pax.is_visible():
                     btn_pax = self.page.get_by_role("button", name=re.compile(r"passenger|passageiro", re.I)).first
                
                btn_pax.click()
                time.sleep(0.5)
                
                # Botão +
                self.page.locator("button[aria-label*='Add'], button[aria-label*='Adicionar']").first.click()
                
                # Botão Done
                self.page.get_by_role("button", name=re.compile(r"Done|Concluído", re.I)).first.click()
                
                # Espera Loading
                time.sleep(1.5)
                self.page.wait_for_load_state("domcontentloaded")
                
                # 4. RE-VERIFICAÇÃO
                # O Google recria o DOM. Precisamos buscar o cartão de novo.
                found_again = False
                cards_now = self.page.locator("li, div[role='listitem']").all()
                for c in cards_now:
                    t = c.inner_text()
                    # Verifica se o voo AA 930 AINDA está na tela
                    if row['Numero'] in t and row['Cia'] in t:
                        found_again = True
                        break
                
                if found_again:
                    confirmed_seats = n
                else:
                    return confirmed_seats, "Limite Atingido (Voo sumiu)", None, extracted_info
            
            return confirmed_seats, "Capacidade Máxima", None, extracted_info

        except Exception as e:
            return -1, f"Erro: {str(e)}", self.page.screenshot(), "Erro"

# --- INTERFACE ---
st.title("✈️ Scanner de Capacidade (Correção de Detecção)")
st.markdown("Este robô lê a lista inteira de voos para encontrar o seu, mesmo se o texto estiver quebrado.")

with st.sidebar:
    st.header("Configurações")
    show_browser = st.checkbox("Ver Navegador (Headless False)", value=True, help="Essencial para debug!")
    cabin = st.selectbox("Classe", ["Econômica", "Executiva", "Primeira"], index=2)
    max_pax = st.slider("Max Passageiros", 1, 9, 9)
    year_ref = st.number_input("Ano", 2025, 2030, 2026)

t1, t2 = st.tabs(["📋 Lista de Voos", "✍️ Manual"])
df_input = pd.DataFrame()

with t1:
    txt = st.text_area("Cole aqui (Ex: Seat Counts GRU-MIA ... AA 930 ... Jan 17)", height=150)
    if txt:
        parsed = parse_text(txt, year_ref)
        if not parsed.empty:
            st.success(f"{len(parsed)} voos identificados.")
            df_input = parsed

with t2:
    base = df_input if not df_input.empty else pd.DataFrame([{"Voo Completo": "AA 930", "Numero": "930", "Cia": "AA", "Origem": "GRU", "Destino": "MIA", "Data": datetime(2026, 1, 17)}])
    edited = st.data_editor(base, num_rows="dynamic", use_container_width=True, column_config={"Data": st.column_config.DateColumn(format="DD/MM/YYYY")})
    if not edited.empty:
        df_input = edited

if st.button("🚀 Iniciar Varredura", type="primary"):
    if df_input.empty:
        st.error("Adicione voos.")
    else:
        bot = FlightBot(headless=not show_browser)
        results = []
        status = st.status("Iniciando...", expanded=True)
        
        try:
            bot.start()
            total = len(df_input)
            
            for i, row in df_input.iterrows():
                status.write(f"🔎 ({i+1}/{total}) Buscando **{row['Voo Completo']}**...")
                
                seats, msg, img, info_extra = bot.check_flight(row, cabin, max_pax, True)
                
                results.append({
                    "Voo": row['Voo Completo'],
                    "Rota": f"{row['Origem']}-{row['Destino']}",
                    "Data": row['Data'],
                    "Assentos": seats,
                    "Info": info_extra,
                    "Status": msg
                })
                
                if seats <= 0 and img:
                    st.image(img, caption=f"Erro no voo {row['Voo Completo']}", width=400)
            
            bot.stop()
            status.update(label="Concluído!", state="complete", expanded=False)
            
            # Exibir e Baixar
            res_df = pd.DataFrame(results)
            st.dataframe(res_df.style.map(lambda x: 'background-color: #ffcdd2' if x==0 else 'background-color: #c8e6c9', subset=['Assentos']), use_container_width=True)
            
            st.download_button("📥 Baixar Excel", to_excel(res_df), "resultado_voos.xlsx")
            
        except Exception as e:
            bot.stop()
            st.error(f"Erro: {e}")
