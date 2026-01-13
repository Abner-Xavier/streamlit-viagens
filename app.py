import streamlit as st
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import subprocess
import io
from datetime import datetime, timedelta

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Scanner de Voos para Excel", page_icon="📊", layout="wide")

# --- INSTALAÇÃO AUTOMÁTICA ---
def install_playwright():
    if 'playwright_installed' not in st.session_state:
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True)
            st.session_state['playwright_installed'] = True
        except Exception:
            pass

install_playwright()

# --- FUNÇÕES AUXILIARES ---
def parse_seat_counts_text(text, year):
    """Lê o formato 'Seat Counts ORIGEM-DESTINO ...' e transforma em Tabela"""
    flights = []
    # Regex flexível para capturar: AAA-BBB ... XX 123 ... MMM DD
    regex_pattern = r"([A-Z]{3})-([A-Z]{3}).*?([A-Z0-9]{2}\s?\d{1,4}).*?([A-Za-z]{3}\s\d{1,2})"
    
    lines = text.strip().split('\n')
    for line in lines:
        match = re.search(regex_pattern, line)
        if match:
            origin, dest, flight_num, date_part = match.groups()
            try:
                # Converte "Jan 17" + Ano para Data Real
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

def convert_df_to_excel(df):
    """Converte DataFrame para binário Excel para download"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Resultados')
    processed_data = output.getvalue()
    return processed_data

# --- CLASSE DO SCANNER ---
class ExcelFlightScanner:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        playwright = sync_playwright().start()
        self.browser = playwright.chromium.launch(
            headless=True, # Mude para False se quiser ver o robô
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

    def check_availability(self, row, cabin_class, max_pax, one_way):
        try:
            # 1. Monta a URL (Método mais rápido e estável que preencher form)
            origin = row['Origem'].upper()
            dest = row['Destino'].upper()
            flight_num = row['Voo']
            date_str = row['Data'].strftime("%Y-%m-%d") # Formato YYYY-MM-DD para URL
            
            cabin_map = {"Econômica": "economy", "Executiva": "business", "Primeira": "first"}
            cabin_query = cabin_map.get(cabin_class, "economy")
            trip_type = "one way" if one_way else "round trip"

            # Busca Google: "Flights from GRU to MIA on 2026-01-15 AA930 one way business class"
            search_query = f"Flights from {origin} to {dest} on {date_str} {flight_num} {trip_type} {cabin_query} class"
            encoded_query = search_query.replace(" ", "+")
            url = f"https://www.google.com/travel/flights?q={encoded_query}"
            
            self.page.goto(url, timeout=45000)
            
            # Fecha cookies/popups
            try: self.page.get_by_role("button", name=re.compile(r"Reject|Rejeitar|Accept|Aceitar", re.I)).first.click(timeout=3000)
            except: pass
            
            self.page.wait_for_load_state("networkidle")

            # Regex para confirmar se o voo certo está na tela
            clean_num = flight_num.replace(" ", "")
            letters = "".join(re.findall(r"[a-zA-Z]+", clean_num))
            numbers = "".join(re.findall(r"\d+", clean_num))
            # Procura por "AA" e "930" próximos
            flight_regex = re.compile(f"{letters}\\s*{numbers}", re.I)

            # Verifica se o card do voo existe
            card = self.page.locator("li, div[role='listitem']").filter(has_text=flight_regex).first
            if not card.is_visible():
                return 0, "Voo não encontrado (Verifique Data/Rota)"

            confirmed_seats = 1
            
            # Loop de incremento de passageiros
            for n in range(2, max_pax + 1):
                # Abre Pax
                btn_pax = self.page.locator("div[jsaction*='click']").filter(has_text=re.compile(r"^\d+$|passenger", re.I)).first
                if not btn_pax.is_visible(): break
                btn_pax.click()
                
                # Clica Add Adulto
                self.page.locator("button[aria-label*='Add'], button[aria-label*='Adicionar']").first.click()
                
                # Clica Done
                self.page.get_by_role("button", name=re.compile(r"Done|Concluído", re.I)).first.click()
                
                # Aguarda update
                time.sleep(1.0)
                self.page.wait_for_load_state("domcontentloaded")
                
                # Checa se voo sumiu
                card = self.page.locator("li, div[role='listitem']").filter(has_text=flight_regex).first
                if card.is_visible():
                    confirmed_seats = n
                else:
                    return confirmed_seats, "Limite atingido (Voo sumiu)"
            
            return confirmed_seats, "Capacidade máxima verificada"

        except Exception as e:
            return -1, f"Erro: {str(e)}"

# --- INTERFACE DO USUÁRIO ---
st.title("📊 Scanner de Voos Automático")
st.markdown("Insira os dados, verifique a disponibilidade e baixe a planilha Excel.")

# Sidebar de Configurações
with st.sidebar:
    st.header("Configurações")
    cabin = st.selectbox("Classe", ["Econômica", "Econômica Premium", "Executiva", "Primeira"], index=2)
    max_pax = st.slider("Testar até quantos passageiros?", 1, 9, 9)
    one_way = st.checkbox("Apenas Ida (One Way)", value=True)
    target_year = st.number_input("Ano da Viagem (para Textos)", 2025, 2030, 2026)

# Abas de Entrada
tab_text, tab_table = st.tabs(["📝 Colar Texto (Batch)", "📅 Tabela Manual"])

df_input = pd.DataFrame()

with tab_text:
    st.caption("Cole linhas no formato: 'Seat Counts GRU-MIA ... AA 930 ... Jan 17'")
    raw_text = st.text_area("Lista de Voos", height=150)
    if raw_text:
        df_parsed = parse_seat_counts_text(raw_text, target_year)
        if not df_parsed.empty:
            st.info(f"{len(df_parsed)} voos identificados.")
            df_input = df_parsed
        else:
            st.warning("Formato não reconhecido.")

with tab_table:
    st.caption("Adicione voos manualmente na tabela abaixo:")
    # Tabela editável
    empty_df = pd.DataFrame(columns=["Voo", "Origem", "Destino", "Data"])
    # Se já tiver dados do texto, usa eles, senão cria linhas vazias
    data_source = df_input if not df_input.empty else pd.DataFrame([{"Voo": "AA 930", "Origem": "GRU", "Destino": "MIA", "Data": datetime(2026, 1, 17)}])
    
    edited_df = st.data_editor(
        data_source,
        num_rows="dynamic",
        column_config={
            "Data": st.column_config.DateColumn("Data da Viagem", format="DD/MM/YYYY")
        },
        use_container_width=True
    )
    # A tabela manual tem prioridade se for modificada
    if not edited_df.empty:
        df_input = edited_df

# Botão de Ação
st.divider()
col_action, col_download = st.columns([1, 1])

if "results" not in st.session_state:
    st.session_state.results = None

with col_action:
    if st.button("🚀 Iniciar Varredura e Gerar Excel", type="primary", use_container_width=True):
        if df_input.empty:
            st.error("Adicione voos na tabela ou cole o texto primeiro.")
        else:
            scanner = ExcelFlightScanner()
            results_list = []
            
            # Barra de progresso
            prog_bar = st.progress(0)
            status_box = st.status("Iniciando navegador...", expanded=True)
            
            try:
                scanner.start()
                total = len(df_input)
                
                for idx, row in df_input.iterrows():
                    # Validação básica
                    if pd.isna(row['Voo']) or pd.isna(row['Origem']): continue
                    
                    status_box.write(f"✈️ ({idx+1}/{total}) Analisando **{row['Voo']}** ({row['Origem']} -> {row['Destino']})...")
                    
                    seats, msg = scanner.check_availability(row, cabin, max_pax, one_way)
                    
                    results_list.append({
                        "Voo": row['Voo'],
                        "Origem": row['Origem'],
                        "Destino": row['Destino'],
                        "Data": row['Data'],
                        "Classe": cabin,
                        "Assentos Disponíveis": seats if seats >= 0 else 0,
                        "Status": msg if seats >= 0 else "Erro",
                        "Detalhe": msg
                    })
                    
                    prog_bar.progress((idx + 1) / total)
                
                scanner.stop()
                status_box.update(label="Varredura Completa!", state="complete", expanded=False)
                
                # Salva resultados na sessão
                st.session_state.results = pd.DataFrame(results_list)
                st.balloons()
                
            except Exception as e:
                scanner.stop()
                st.error(f"Ocorreu um erro: {e}")

# Exibição e Download
if st.session_state.results is not None:
    res_df = st.session_state.results
    
    st.subheader("📋 Resultados")
    # Estiliza a tabela: Verde se tiver assentos, Vermelho se for 0
    st.dataframe(
        res_df.style.map(lambda x: 'background-color: #ffcdd2' if x == 0 else 'background-color: #c8e6c9', subset=['Assentos Disponíveis']),
        use_container_width=True
    )
    
    # Gera o Excel
    excel_data = convert_df_to_excel(res_df)
    
    with col_download:
        st.download_button(
            label="📥 Baixar Tabela em Excel (.xlsx)",
            data=excel_data,
            file_name="disponibilidade_voos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
