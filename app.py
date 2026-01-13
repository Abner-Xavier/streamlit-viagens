import streamlit as st
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import subprocess
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Scanner com XPaths Customizados", page_icon="🕵️", layout="wide")

# --- INSTALAÇÃO AUTOMÁTICA ---
def install_playwright():
    if 'playwright_installed' not in st.session_state:
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True)
            st.session_state['playwright_installed'] = True
        except Exception:
            pass

# --- PARSER DE TEXTO ---
def parse_flight_text(text_input, year):
    flights = []
    regex_pattern = r"([A-Z]{3})-([A-Z]{3}).*?([A-Z0-9]{2}\s?\d{1,4}).*?([A-Za-z]{3}\s\d{1,2})"
    lines = text_input.strip().split('\n')
    for line in lines:
        match = re.search(regex_pattern, line)
        if match:
            origin, dest, flight_num, date_part = match.groups()
            try:
                date_obj = datetime.strptime(f"{date_part} {year}", "%b %d %Y")
                flights.append({
                    "Origem": origin,
                    "Destino": dest,
                    "Voo": flight_num.strip(),
                    "DataDisplay": date_obj.strftime("%d/%m/%Y"), # Formato para digitar no input
                    "DataIso": date_obj.strftime("%Y-%m-%d"),
                    "RawLine": line
                })
            except ValueError:
                continue
    return pd.DataFrame(flights)

# --- CLASSE DO ROBÔ ---
class FormScanner:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None

    def start(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=True, # Mude para False se quiser assistir
            args=["--disable-blink-features=AutomationControlled"]
        )
        self.context = self.browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.page = self.context.new_page()

    def stop(self):
        if self.browser: self.browser.close()
        if self.playwright: self.playwright.stop()

    def run_search_and_scan(self, row, cabin_class, max_pax, status_log):
        try:
            # 1. ACESSAR URL
            base_url = "https://www.google.com/travel/flights?curr=USD"
            self.page.goto(base_url, timeout=60000)
            
            # Fecha cookies
            try: self.page.get_by_role("button", name=re.compile(r"Reject|Rejeitar|Accept|Aceitar", re.I)).first.click(timeout=3000)
            except: pass

            # --- PREENCHIMENTO INICIAL ---
            
            # A. Só Ida (XPath anterior)
            try:
                self.page.locator('xpath=//*[@id="yDmH0d"]/c-wiz[2]/div/div[2]/c-wiz/div[1]/c-wiz/div[2]/div[1]/div[1]/div[1]/div/div[1]/div[1]/div/div/div/div[1]/div').click(timeout=2000)
                self.page.get_by_text("One way").click()
            except: pass # Pode já estar selecionado

            # B. Origem
            try:
                inp = self.page.locator('xpath=//*[@id="i23"]/div[1]/div/div/div[1]/div/div/input').first
                if not inp.is_visible(): inp = self.page.get_by_role("combobox", name=re.compile("Where from|De onde", re.I)).first
                inp.click(); inp.clear(); inp.fill(row['Origem']); time.sleep(0.5); self.page.keyboard.press("Enter")
            except: pass

            # C. Destino
            try:
                inp = self.page.locator('xpath=//*[@id="i23"]/div[4]/div/div/div[1]/div/div/input').first
                if not inp.is_visible(): inp = self.page.get_by_role("combobox", name=re.compile("Where to|Para onde", re.I)).first
                inp.click(); inp.clear(); inp.fill(row['Destino']); time.sleep(0.5); self.page.keyboard.press("Enter")
            except: pass

            # D. Data
            try:
                xpath_date = '//*[@id="yDmH0d"]/c-wiz[2]/div/div[2]/c-wiz/div[1]/c-wiz/div[2]/div[1]/div[1]/div[1]/div/div[2]/div[2]/div/div/div[1]/div/div/div[1]/div/div[1]/div/input'
                inp = self.page.locator(f"xpath={xpath_date}").first
                if not inp.is_visible(): inp = self.page.get_by_role("textbox", name=re.compile("Departure|Partida", re.I)).first
                inp.click(); time.sleep(0.2); self.page.keyboard.press("Control+a"); self.page.keyboard.press("Backspace")
                inp.fill(row['DataDisplay']); time.sleep(0.5); self.page.keyboard.press("Enter")
                # Fecha calendário clicando fora ou no Done
                self.page.get_by_role("button", name=re.compile("Done|Concluído|Search", re.I)).last.click()
            except: pass

            # E. Classe (Seus XPaths)
            try:
                self.page.locator('xpath=//*[@id="yDmH0d"]/c-wiz[2]/div/div[2]/c-wiz/div[1]/c-wiz/div[2]/div[1]/div[1]/div[1]/div/div[1]/div[3]/div/div/div/div[1]/div').click()
                time.sleep(0.5)
                if cabin_class == "Primeira":
                    self.page.locator('xpath=//*[@id="yDmH0d"]/c-wiz[2]/div/div[2]/c-wiz/div[1]/c-wiz/div[2]/div[1]/div[1]/div[1]/div/div[1]/div[3]/div/div/div/div[2]/ul/li[4]').click()
                elif cabin_class == "Executiva":
                    self.page.locator('xpath=//*[@id="yDmH0d"]/c-wiz[2]/div/div[2]/c-wiz/div[1]/c-wiz/div[2]/div[1]/div[1]/div[1]/div/div[1]/div[3]/div/div/div/div[2]/ul/li[3]').click()
                else:
                    self.page.locator("li").first.click() # Fallback Eco
            except: pass

            # Aguarda carregamento inicial
            status_log.write("🔎 Buscando voos...")
            self.page.wait_for_load_state("networkidle")
            time.sleep(2)

            # Regex para validar voo
            clean_num = row['Voo'].replace(" ", "")
            letters = "".join(re.findall(r"[a-zA-Z]+", clean_num))
            numbers = "".join(re.findall(r"\d+", clean_num))
            flight_regex = re.compile(f"{letters}\\s*{numbers}", re.I)

            # Verifica existência inicial
            if not self.page.locator("li, div[role='listitem']").filter(has_text=flight_regex).first.is_visible():
                return 0, "Voo não encontrado na busca inicial"

            confirmed = 1

            # --- LOOP DE PASSAGEIROS USANDO SEUS XPATHS ---
            # SEUS XPATHS DE PASSAGEIRO:
            xp_pax_menu = '//*[@id="yDmH0d"]/c-wiz[2]/div/div[2]/c-wiz/div[1]/c-wiz/div[2]/div[1]/div[1]/div[1]/div/div[1]/div[2]/div/div[1]/div/button/div[3]'
            xp_add_adult = '//*[@id="i10-1"]/div/span[3]/button/div[3]' # Botão +
            xp_done_btn = '//*[@id="ow11"]/div[2]/div[2]/button[1]/span' # Botão Done
            
            # Nota: O XPath do contador (1 adulto/2 adultos) usamos apenas visualmente, não clicamos nele.

            for n in range(2, max_pax + 1):
                status_log.write(f"🔢 Testando **{n}** passageiros...")

                # 1. ABRIR MENU (PAX)
                try:
                    # Tenta seu XPath Exato
                    self.page.locator(f"xpath={xp_pax_menu}").click(timeout=2000)
                except:
                    # Fallback: Tenta achar o botão que tem ícone de usuário
                    self.page.locator("div[jsaction*='click']").filter(has_text=re.compile(r"^\d+$|passenger", re.I)).first.click()

                time.sleep(0.5)

                # 2. ADICIONAR ADULTO (Clicar no +)
                try:
                    # Tenta seu XPath Exato (i10-1...)
                    self.page.locator(f"xpath={xp_add_adult}").click(timeout=2000)
                except:
                    # Fallback: Botão com aria-label Add/Adicionar
                    self.page.locator("button[aria-label*='Add'], button[aria-label*='Adicionar']").first.click()

                time.sleep(0.5)

                # 3. FECHAR MENU (Done)
                try:
                    # Tenta seu XPath Exato (ow11...)
                    self.page.locator(f"xpath={xp_done_btn}").click(timeout=2000)
                except:
                    # Fallback: Botão Done por texto
                    self.page.get_by_role("button", name=re.compile(r"Done|Concluído", re.I)).first.click()

                # 4. AGUARDAR REFRESH
                # Ao mudar pax, o Google recarrega a lista
                time.sleep(1.5)
                self.page.wait_for_load_state("domcontentloaded")

                # 5. VERIFICAR SE O VOO AINDA EXISTE
                flight_card = self.page.locator("li, div[role='listitem']").filter(has_text=flight_regex).first
                
                if flight_card.is_visible():
                    confirmed = n
                else:
                    return confirmed, "Limite atingido"

            return confirmed, "Capacidade máxima"

        except Exception as e:
            return -1, f"Erro: {str(e)}"

# --- INTERFACE STREAMLIT ---
install_playwright()
st.title("🕵️ Scanner de Assentos (XPath Custom)")

col1, col2 = st.columns([2, 1])

with col1:
    raw_text = st.text_area("Lista de Voos:", height=150, placeholder="Seat Counts GRU-MIA Dep 11:30PM AA 930 – Jan 17")

with col2:
    year = st.number_input("Ano", 2024, 2030, 2026)
    cabin = st.selectbox("Classe", ["Econômica", "Executiva", "Primeira"])
    max_pax = st.slider("Max Passageiros", 1, 9, 9)

if st.button("🚀 Iniciar Scanner", type="primary"):
    if raw_text:
        df = parse_flight_text(raw_text, year)
        if not df.empty:
            scanner = FormScanner()
            results = []
            status = st.status("Iniciando...", expanded=True)
            
            try:
                scanner.start()
                for idx, row in df.iterrows():
                    status.write(f"✈️ Processando **{row['Voo']}** ({idx+1}/{len(df)})...")
                    seats, msg = scanner.run_search_and_scan(row, cabin, max_pax, status)
                    results.append({"Voo": row['Voo'], "Assentos": seats, "Obs": msg})
                
                scanner.stop()
                status.update(label="Concluído", state="complete")
                st.dataframe(pd.DataFrame(results).style.map(lambda x: 'color: red' if x==0 else 'color: green', subset=['Assentos']))
            except Exception as e:
                scanner.stop()
                st.error(str(e))
        else:
            st.warning("Nenhum voo detectado.")
