import streamlit as st
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import subprocess
import io
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Extrator de Números de Voo", page_icon="✈️", layout="wide")

# --- INSTALAÇÃO ---
def install_playwright():
    if 'playwright_installed' not in st.session_state:
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True)
            st.session_state['playwright_installed'] = True
        except Exception:
            pass

install_playwright()

# --- MOTOR DE EXTRAÇÃO ---
def extract_flight_numbers(origin, dest, date_obj, cabin_class):
    data = []
    
    with sync_playwright() as p:
        # Modo Anônimo para evitar bloqueios
        browser = p.chromium.launch(
            headless=True,
            args=["--incognito", "--disable-blink-features=AutomationControlled"]
        )
        page = browser.new_page(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Montar URL
        date_str = date_obj.strftime("%Y-%m-%d")
        cabin_map = {"Econômica": "economy", "Executiva": "business", "Primeira": "first"}
        url = f"https://www.google.com/travel/flights?q=Flights%20from%20{origin}%20to%20{dest}%20on%20{date_str}%20one%20way%20{cabin_map[cabin_class]}%20class"
        
        try:
            st.toast("Acessando Google Flights...", icon="📡")
            page.goto(url, timeout=60000)
            
            # Limpa Cookies/Popups
            try: page.get_by_role("button", name=re.compile(r"Reject|Aceitar", re.I)).first.click(timeout=3000)
            except: pass
            
            page.wait_for_load_state("networkidle")
            
            # Tenta expandir lista ("Ver mais voos")
            try:
                btn = page.locator("button").filter(has_text=re.compile(r"View more|Ver mais", re.I)).first
                if btn.is_visible():
                    btn.click()
                    time.sleep(2)
            except: pass
            
            # Rola para carregar tudo
            page.mouse.wheel(0, 4000)
            time.sleep(1.5)
            
            # --- EXTRAÇÃO INTELIGENTE DE CÓDIGOS ---
            # O Google Flights geralmente coloca o número do voo em elementos pequenos no rodapé do cartão
            # ou junto com o nome da Cia. Vamos pegar todos os textos e filtrar com Regex.
            
            cards = page.locator("li, div[role='listitem']").all()
            
            for card in cards:
                text = card.inner_text()
                
                # Regex para encontrar Horário (00:00) - Validador de que é um voo
                if not re.search(r"\d{1,2}:\d{2}", text): continue
                
                # 1. Extração de Horários e Preço (para contexto)
                times = re.findall(r"(\d{1,2}:\d{2}\s?[AP]?M?)", text)
                price_match = re.search(r"((?:R\$|\$|€|£)\s?[\d,.]+)", text)
                price = price_match.group(1) if price_match else "N/A"
                
                # 2. Extração do Número do Voo
                # Procura padrões comuns como "LA 3055", "AA 930", "G3 1234"
                # A regex procura: 2 letras maiúsculas + espaço opcional + 2 a 4 números
                # Excluindo padrões de horário e moeda
                flight_codes = re.findall(r"(?<!\$)(\b[A-Z0-9]{2}\s?\d{2,4}\b)", text)
                
                # Filtra códigos falsos (como KG do CO2e ou AM/PM)
                valid_codes = []
                for code in flight_codes:
                    if "CO2" not in code and "PM" not in code and "AM" not in code and "KG" not in code:
                        valid_codes.append(code)
                
                # Se achou código, adiciona na lista
                if valid_codes:
                    # Remove duplicatas e junta (ex: voo com conexão pode ter 2 números)
                    code_final = " / ".join(list(set(valid_codes)))
                else:
                    # Fallback: Se não achou código explícito, tenta pegar a Cia Aérea
                    # Geralmente a primeira linha ou logo após o horário
                    lines = text.split('\n')
                    code_final = "Verificar Cia (" + (lines[1] if len(lines) > 1 else "N/A") + ")"

                # Verifica se é voo direto ou com paradas
                stops = "Direto"
                if "1 stop" in text or "1 parada" in text: stops = "1 Parada"
                elif "stop" in text or "parada" in text: stops = "+1 Parada"

                if len(times) >= 1:
                    data.append({
                        "Número do Voo": code_final,
                        "Partida": times[0],
                        "Chegada": times[1] if len(times) > 1 else "?",
                        "Paradas": stops,
                        "Preço": price
                    })

        except Exception as e:
            st.error(f"Erro: {e}")
            
        browser.close()
        return pd.DataFrame(data)

# --- INTERFACE ---
st.title("🔍 Pesquisador de Números de Voos")
st.markdown("Descubra os códigos de voo (ex: AA 930) para uma rota e data.")

with st.sidebar:
    st.header("Configuração")
    origin = st.text_input("Origem", "GRU", max_chars=3).upper()
    dest = st.text_input("Destino", "MIA", max_chars=3).upper()
    date_val = st.date_input("Data", min_value=datetime.today())
    cabin = st.selectbox("Classe", ["Econômica", "Executiva", "Primeira"])

if st.button("🚀 Pesquisar Voos", type="primary", use_container_width=True):
    if origin and dest:
        with st.status("Varrendo voos...", expanded=True) as status:
            df = extract_flight_numbers(origin, dest, date_val, cabin)
            
            if not df.empty:
                status.update(label="Concluído!", state="complete", expanded=False)
                
                # Mostra estatísticas
                st.metric("Voos Encontrados", len(df))
                
                # Tabela principal
                st.dataframe(df, use_container_width=True)
                
                # Download Excel
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False)
                
                st.download_button(
                    "📥 Baixar Lista (.xlsx)",
                    data=output.getvalue(),
                    file_name=f"voos_{origin}_{dest}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                status.update(label="Nenhum voo encontrado", state="error")
                st.warning("Tente outra data ou verifique se o Google pediu Captcha.")
    else:
        st.warning("Preencha a rota.")
