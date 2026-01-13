import streamlit as st
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import subprocess
import io
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Scanner Geral de Voos", page_icon="🌎", layout="wide")

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
def scrape_all_flights(origin, dest, date_obj, cabin_class):
    data = []
    
    with sync_playwright() as p:
        # Browser Invisível (Headless)
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        page = browser.new_page(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        # URL
        date_str = date_obj.strftime("%Y-%m-%d")
        cabin_map = {"Econômica": "economy", "Executiva": "business", "Primeira": "first"}
        cabin = cabin_map.get(cabin_class, "economy")
        
        query = f"Flights from {origin} to {dest} on {date_str} one way {cabin} class"
        url = f"https://www.google.com/travel/flights?q={query.replace(' ', '+')}"
        
        try:
            st.toast("Acessando Google Flights...", icon="🌎")
            page.goto(url, timeout=60000)
            
            # Limpa Cookies
            try: page.get_by_role("button", name=re.compile(r"Reject|Aceitar", re.I)).first.click(timeout=3000)
            except: pass
            
            page.wait_for_load_state("networkidle")
            
            # --- ROLAGEM E EXPANSÃO ---
            # O Google esconde voos. Precisamos clicar em "Ver mais voos" se existir.
            try:
                btn_more = page.locator("button").filter(has_text="View more flights").or_(page.locator("button").filter(has_text="Ver mais voos"))
                if btn_more.is_visible():
                    btn_more.click()
                    time.sleep(2)
            except:
                pass
            
            # Scroll para carregar lazy loading
            page.mouse.wheel(0, 3000)
            time.sleep(1)
            
            # --- COLETA DE DADOS ---
            # Pega todos os cartões de lista
            cards = page.locator("li, div[role='listitem']").all()
            
            total_found = 0
            
            for card in cards:
                text = card.inner_text()
                
                # Filtro Básico: Tem cara de voo? (Tem horário AM/PM ou :)
                if not re.search(r"\d{1,2}:\d{2}", text):
                    continue
                
                # Extração via Regex
                # 1. Horários (Ex: 8:45 PM – 5:30 AM)
                times = re.findall(r"(\d{1,2}:\d{2}\s?[AP]?M?)", text)
                if len(times) < 2: continue # Precisa ter partida e chegada
                
                # 2. Preço (Ex: $5,006 ou R$ 5.006)
                price_match = re.search(r"((?:R\$|\$|€|£)\s?[\d,.]+)", text)
                price = price_match.group(1) if price_match else "N/A"
                
                # 3. Duração
                duration_match = re.search(r"(\d+\s?hr\s?\d*\s?min|\d+\s?h\s?\d*\s?m)", text)
                duration = duration_match.group(1) if duration_match else ""
                
                # 4. Cia Aérea e Paradas
                # Aqui é heurística: removemos o que já achamos e limpamos o texto
                # Geralmente a Cia aparece no começo ou meio. Vamos salvar o texto bruto limpo para análise.
                clean_text = text.replace("\n", " | ")
                
                # Tenta identificar paradas
                stops = "Direto" if "Nonstop" in text or "Direto" in text else "Com paradas"
                if "1 stop" in text or "1 parada" in text: stops = "1 Parada"
                
                data.append({
                    "Partida": times[0],
                    "Chegada": times[1] if len(times) > 1 else "?",
                    "Duração": duration,
                    "Preço": price,
                    "Paradas": stops,
                    "Texto Bruto (Ref)": clean_text[:100] # Corta para não ficar gigante
                })
                total_found += 1
                
        except Exception as e:
            st.error(f"Erro na extração: {e}")
            
        browser.close()
        return pd.DataFrame(data)

# --- INTERFACE ---
st.title("📊 Extrator de Voos para Excel")
st.markdown("Identifica **todos** os voos disponíveis na página (melhores e outros) e salva em planilha.")

with st.sidebar:
    st.header("Dados da Viagem")
    origin = st.text_input("Origem", "GRU", max_chars=3).upper()
    dest = st.text_input("Destino", "MIA", max_chars=3).upper()
    date_val = st.date_input("Data", min_value=datetime.today())
    cabin = st.selectbox("Classe", ["Econômica", "Executiva", "Primeira"])

if st.button("🚀 Pesquisar e Gerar Excel", type="primary", use_container_width=True):
    if origin and dest:
        with st.status("Varrendo o Google Flights...", expanded=True) as status:
            status.write("🔍 Iniciando navegador...")
            df_result = scrape_all_flights(origin, dest, date_val, cabin)
            
            if not df_result.empty:
                status.write(f"✅ Encontrados {len(df_result)} voos!")
                status.update(label="Concluído!", state="complete", expanded=False)
                
                st.divider()
                st.subheader("Resultados Encontrados")
                
                # Mostra tabela na tela
                st.dataframe(df_result, use_container_width=True)
                
                # Botão Download
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_result.to_excel(writer, index=False)
                
                file_name = f"voos_{origin}_{dest}_{date_val}.xlsx"
                
                st.download_button(
                    label="📥 Baixar Planilha (.xlsx)",
                    data=output.getvalue(),
                    file_name=file_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                status.update(label="Nenhum voo encontrado", state="error")
                st.error("Não foi possível extrair dados. O Google pode ter pedido CAPTCHA ou não há voos.")
    else:
        st.warning("Preencha Origem e Destino.")
