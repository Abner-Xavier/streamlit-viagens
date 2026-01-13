import streamlit as st
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import subprocess
import io
import os
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Scanner Master - Google Flights", page_icon="✈️", layout="wide")

# --- INSTALAÇÃO AUTOMÁTICA ---
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
    lines = text.strip().split('\n')
    for line in lines:
        try:
            # Regex ajustado para capturar padrões variados
            flight_match = re.search(r"([A-Z0-9]{2})\s?(\d{2,4})", line)
            route_match = re.search(r"([A-Z]{3})-([A-Z]{3})", line)
            date_match = re.search(r"([A-Za-z]{3}\s\d{1,2})", line)
            
            if flight_match and route_match and date_match:
                date_obj = datetime.strptime(f"{date_match.group(1)} {year}", "%b %d %Y")
                flights.append({
                    "Voo Completo": f"{flight_match.group(1)} {flight_match.group(2)}",
                    "Numero": flight_match.group(2),
                    "Cia": flight_match.group(1),
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
        
        # Tenta lançar o navegador. Se falhar por falta de monitor (XServer), força headless.
        try:
            self.browser = p.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"]
            )
        except Exception as e:
            if "Missing X server" in str(e) or not self.headless:
                print("⚠️ Ambiente sem monitor detectado. Forçando modo Headless.")
                self.browser = p.chromium.launch(
                    headless=True, # Força invisível para não quebrar no servidor
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
                )
            else:
                raise e

        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 900},
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
            
            query = f"Flights from {row['Origem']} to {row['Destino']} on {date_str} {trip} {cabin_map[cabin_class]} class"
            url = f"https://www.google.com/travel/flights?q={query.replace(' ', '+')}"
            
            self.page.goto(url, timeout=60000)
            try: self.page.get_by_role("button", name=re.compile(r"Reject|Aceitar", re.I)).first.click(timeout=3000)
            except: pass
            
            self.page.wait_for_load_state("networkidle")
            time.sleep(3)

            # 2. ENCONTRAR O CARTÃO DO VOO
            flight_cards = self.page.locator("li, div[role='listitem']").all()
            
            target_card = None
            extracted_info = "N/A"
            
            # Itera para achar Cia e Numero no mesmo card
            for card in flight_cards:
                text = card.inner_text()
                if row['Numero'] in text and row['Cia'] in text:
                    target_card = card
                    extracted_info = "Card encontrado"
                    break
            
            if not target_card:
                return 0, "Voo não encontrado (Cia/Num não batem)", self.page.screenshot(), "---"

            # 3. TESTAR PASSAGEIROS
            confirmed_seats = 1
            
            for n in range(2, max_pax + 1):
                # Menu Pax
                btn_pax = self.page.locator("div[jsaction*='click']").filter(has_text=re.compile(r"^\d+$|passenger|passageiro", re.I)).first
                if not btn_pax.is_visible():
                     btn_pax = self.page.get_by_role("button", name=re.compile(r"passenger|passageiro", re.I)).first
                
                if btn_pax.is_visible():
                    btn_pax.click()
                    time.sleep(0.5)
                    # Add
                    self.page.locator("button[aria-label*='Add'], button[aria-label*='Adicionar']").first.click()
                    # Done
                    self.page.get_by_role("button", name=re.compile(r"Done|Concluído", re.I)).first.click()
                    
                    time.sleep(1.5)
                    self.page.wait_for_load_state("domcontentloaded")
                    
                    # Re-verificação
                    found_again = False
                    cards_now = self.page.locator("li, div[role='listitem']").all()
                    for c in cards_now:
                        t = c.inner_text()
                        if row['Numero'] in t and row['Cia'] in t:
                            found_again = True
                            break
                    
                    if found_again:
                        confirmed_seats = n
                    else:
                        return confirmed_seats, "Limite Atingido (Voo sumiu)", None, extracted_info
            
            return confirmed_seats, "Capacidade Máxima", None, extracted_info

        except Exception as e:
            # Tenta tirar screenshot se a página estiver aberta
            img = None
            try: img = self.page.screenshot()
            except: pass
            return -1, f"Erro: {str(e)}", img, "Erro"

# --- INTERFACE ---
st.title("✈️ Scanner de Capacidade (Cloud Ready)")
st.markdown("Este robô foi ajustado para rodar no Streamlit Cloud sem erros de display.")

with st.sidebar:
    st.header("Configurações")
    
    # Checkbox ajustado: Se estiver na nuvem, ignoramos o pedido de ver o browser
    show_browser = st.checkbox("Ver Navegador (Apenas Local)", value=False, help="Marque APENAS se estiver rodando no seu computador. Na nuvem, isso será ignorado.")
    
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
    edited = st.data_editor(base, num_rows="dynamic", width="stretch", column_config={"Data": st.column_config.DateColumn(format="DD/MM/YYYY")})
    if not edited.empty:
        df_input = edited

if st.button("🚀 Iniciar Varredura", type="primary", use_container_width=True):
    if df_input.empty:
        st.error("Adicione voos.")
    else:
        # Inicia Bot (Se show_browser for True mas estiver no servidor, o try/catch na classe resolve)
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
            
            # Correção do use_container_width aqui:
            st.dataframe(
                res_df.style.map(lambda x: 'background-color: #ffcdd2' if x==0 else 'background-color: #c8e6c9', subset=['Assentos']), 
                width="stretch"
            )
            
            st.download_button(
                "📥 Baixar Excel", 
                to_excel(res_df), 
                "resultado_voos.xlsx", 
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
                use_container_width=True
            )
            
        except Exception as e:
            bot.stop()
            st.error(f"Erro: {e}")
            if "Missing X server" in str(e):
                st.warning("Dica: Desmarque a opção 'Ver Navegador' quando rodar no Streamlit Cloud.")
