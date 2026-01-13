import streamlit as st
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import subprocess
import io
import random
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Scanner Pro - Excel", page_icon="🕵️", layout="wide")

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
    # Regex captura: ORIGEM-DESTINO ... (CIA NUMERO) ... DATA
    # Aceita formatos variados de texto colado
    regex_pattern = r"([A-Z]{3})-([A-Z]{3}).*?([A-Z0-9]{2}\s?\d{1,4}).*?([A-Za-z]{3}\s\d{1,2})"
    
    lines = text.strip().split('\n')
    for line in lines:
        match = re.search(regex_pattern, line)
        if match:
            origin, dest, flight_num, date_part = match.groups()
            try:
                date_obj = datetime.strptime(f"{date_part} {year}", "%b %d %Y")
                flights.append({
                    "Voo": flight_num.strip(),
                    "Origem": origin,
                    "Destino": dest,
                    "Data": date_obj.date()
                })
            except ValueError:
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
        # Argumentos para evitar detecção de bot
        self.browser = p.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars"
            ]
        )
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768}
        )
        self.page = self.context.new_page()

    def stop(self):
        if self.browser: self.browser.close()

    def check_flight(self, row, cabin_class, max_pax, one_way):
        err_screenshot = None
        try:
            # 1. Monta URL
            flight_full = row['Voo'] # Ex: AA 954
            # Extrai apenas o número (954) para busca mais segura
            flight_number_only = "".join(re.findall(r"\d+", flight_full))
            
            origin, dest = row['Origem'], row['Destino']
            date_str = row['Data'].strftime("%Y-%m-%d")
            
            cabin_map = {"Econômica": "economy", "Executiva": "business", "Primeira": "first"}
            cabin = cabin_map.get(cabin_class, "economy")
            trip = "one way" if one_way else "round trip"
            
            # URL de busca direta
            query = f"Flights from {origin} to {dest} on {date_str} {trip} {cabin} class"
            url = f"https://www.google.com/travel/flights?q={query.replace(' ', '+')}"
            
            self.page.goto(url, timeout=60000)
            
            # Tenta fechar cookies
            try: self.page.get_by_role("button", name=re.compile(r"Rejeitar|Reject|Aceitar|Accept", re.I)).first.click(timeout=4000)
            except: pass
            
            self.page.wait_for_load_state("networkidle")
            time.sleep(2) # Pausa humana essencial

            # 2. Localizar o Cartão do Voo
            # Estratégia: Procura o cartão que contém o NÚMERO do voo (ex: 954)
            # O Google usa role='listitem' para cada voo
            
            # Tenta achar o container do voo
            flight_card = self.page.locator("li, div[role='listitem']").filter(has_text=flight_number_only).first
            
            # Se não achou de primeira, rola a página (scroll) e tenta de novo
            if not flight_card.is_visible():
                self.page.mouse.wheel(0, 500)
                time.sleep(1)
                flight_card = self.page.locator("li, div[role='listitem']").filter(has_text=flight_number_only).first

            if not flight_card.is_visible():
                # Tira print do erro
                err_screenshot = self.page.screenshot()
                return 0, "Voo não encontrado (Veja Print)", err_screenshot

            # Se chegamos aqui, o voo existe na lista!
            confirmed_seats = 1
            
            # 3. Teste de Assentos (Incremental)
            for n in range(2, max_pax + 1):
                # Localiza botão de pax (dentro do menu superior, não do card)
                # O botão geralmente tem um número (ex: "1")
                btn_pax = self.page.locator("div[jsaction*='click']").filter(has_text=re.compile(r"^\d+$|passenger", re.I)).first
                
                # Se não achar o botão, tenta outro seletor genérico
                if not btn_pax.is_visible():
                     btn_pax = self.page.get_by_role("button", name=re.compile(r"passenger|passageiro", re.I)).first
                
                if btn_pax.is_visible():
                    btn_pax.click()
                    time.sleep(0.5)
                    
                    # Clica no + (Adicionar adulto)
                    self.page.locator("button[aria-label*='Add'], button[aria-label*='Adicionar']").first.click()
                    
                    # Clica Concluído/Done
                    self.page.get_by_role("button", name=re.compile(r"Done|Concluído", re.I)).first.click()
                    
                    # Espera a lista atualizar (loading spinner)
                    time.sleep(1.5) 
                    self.page.wait_for_load_state("domcontentloaded")
                    
                    # Verifica se o CARD do voo ainda está visível
                    flight_card = self.page.locator("li, div[role='listitem']").filter(has_text=flight_number_only).first
                    
                    if flight_card.is_visible():
                        confirmed_seats = n
                    else:
                        # Voo sumiu, limite atingido
                        return confirmed_seats, "Limite Atingido", None
                else:
                    return confirmed_seats, "Erro no Botão Pax", None
            
            return confirmed_seats, "Capacidade Máxima", None

        except Exception as e:
            try: err_screenshot = self.page.screenshot()
            except: pass
            return -1, f"Erro Técnico: {str(e)}", err_screenshot

# --- INTERFACE ---
st.title("🕵️ Scanner de Voos Pro (Debug)")
st.markdown("Verifica disponibilidade e exporta para Excel. Use o modo visual se estiver dando erro.")

# Sidebar
with st.sidebar:
    st.header("⚙️ Configuração")
    # NOVO: Checkbox para ver o navegador
    show_browser = st.checkbox("Ver robô trabalhando (Headless False)", value=False, help="Marque isso se estiver dando 'Voo não encontrado' para ver o que está acontecendo.")
    
    cabin = st.selectbox("Classe", ["Econômica", "Executiva", "Primeira"], index=1)
    max_pax = st.slider("Max Passageiros", 1, 9, 9)
    year_ref = st.number_input("Ano da Viagem", 2025, 2030, 2026)
    one_way = st.checkbox("Só Ida (One Way)", value=True)

# Tabs
t1, t2 = st.tabs(["📝 Texto (Batch)", "📅 Manual"])
df_final_input = pd.DataFrame()

with t1:
    txt = st.text_area("Cole a lista aqui:", height=150, placeholder="Seat Counts GRU-MIA ... AA 930 ... Jan 17")
    if txt:
        parsed = parse_text(txt, year_ref)
        if not parsed.empty:
            st.info(f"{len(parsed)} voos lidos.")
            df_final_input = parsed

with t2:
    base = df_final_input if not df_final_input.empty else pd.DataFrame([{"Voo": "AA 930", "Origem": "GRU", "Destino": "MIA", "Data": datetime(2026, 1, 17)}])
    edited = st.data_editor(base, num_rows="dynamic", use_container_width=True, column_config={"Data": st.column_config.DateColumn(format="DD/MM/YYYY")})
    if not edited.empty:
        df_final_input = edited

# Botão Iniciar
if st.button("🚀 Iniciar Varredura", type="primary"):
    if df_final_input.empty:
        st.error("Insira dados primeiro.")
    else:
        # Inicia Scanner
        bot = FlightBot(headless=not show_browser) # Inverte lógica do checkbox
        results = []
        
        status = st.status("Iniciando...", expanded=True)
        progress = st.progress(0)
        
        try:
            bot.start()
            total = len(df_final_input)
            
            for i, row in df_final_input.iterrows():
                status.write(f"🔎 ({i+1}/{total}) Verificando **{row['Voo']}**...")
                
                seats, msg, img = bot.check_flight(row, cabin, max_pax, one_way)
                
                results.append({
                    "Voo": row['Voo'],
                    "Rota": f"{row['Origem']}-{row['Destino']}",
                    "Data": row['Data'],
                    "Assentos": seats if seats > 0 else 0,
                    "Mensagem": msg
                })
                
                # Se der erro, mostra imagem na hora
                if seats <= 0 and img:
                    st.warning(f"Falha visual no voo {row['Voo']}:")
                    st.image(img, caption="O que o robô viu", width=500)
                
                progress.progress((i+1)/total)
            
            bot.stop()
            status.update(label="Finalizado!", state="complete", expanded=False)
            
            # RESULTADOS
            res_df = pd.DataFrame(results)
            st.session_state['last_result'] = res_df # Salva para não perder
            
        except Exception as e:
            bot.stop()
            st.error(f"Erro fatal: {e}")

# EXIBIÇÃO E DOWNLOAD (Fora do bloco do botão para persistir)
if 'last_result' in st.session_state:
    df_res = st.session_state['last_result']
    
    st.divider()
    st.subheader("📊 Resultado Final")
    
    # Colore a tabela
    def color_rows(val):
        if isinstance(val, int) and val > 0: return 'background-color: #d4edda; color: black' # Verde
        return 'background-color: #f8d7da; color: black' # Vermelho
    
    st.dataframe(df_res.style.map(color_rows, subset=['Assentos']), use_container_width=True)
    
    # Download Excel
    xlsx = to_excel(df_res)
    st.download_button("📥 Baixar Planilha Excel", data=xlsx, file_name="voos_disponibilidade.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
