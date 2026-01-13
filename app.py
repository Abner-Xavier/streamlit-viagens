import streamlit as st
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import subprocess
import io
from datetime import datetime

# --- CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Scanner de Assentos", page_icon="✈️", layout="wide")

# --- INSTALAÇÃO DE DEPENDÊNCIAS ---
def install_playwright():
    if 'playwright_installed' not in st.session_state:
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True)
            st.session_state['playwright_installed'] = True
        except Exception:
            pass

install_playwright()

# --- MOTOR DE BUSCA (SIMPLES E EFICIENTE) ---
def get_available_seats(flights_df, max_pax_check):
    results = []
    
    with sync_playwright() as p:
        # Lança navegador em modo INVISÍVEL (Obrigatório para Nuvem)
        browser = p.chromium.launch(
            headless=True, 
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Barra de progresso geral
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total = len(flights_df)
        
        for index, row in flights_df.iterrows():
            try:
                # 1. Preparar Dados
                flight_num_raw = str(row['Voo']).upper().strip() # Ex: AA 930
                # Separa letras e números (Ex: AA e 930)
                flight_digits = "".join(re.findall(r"\d+", flight_num_raw))
                flight_letters = "".join(re.findall(r"[A-Z]+", flight_num_raw))
                
                origin, dest = row['Origem'], row['Destino']
                date_str = row['Data'].strftime("%Y-%m-%d")
                cabin_map = {"Econômica": "economy", "Executiva": "business", "Primeira": "first"}
                cabin_query = cabin_map.get(row['Classe'], "economy")
                
                status_text.markdown(f"🔎 Verificando **{flight_num_raw}** ({origin} -> {dest})...")
                
                # 2. Montar URL Direta
                query = f"Flights from {origin} to {dest} on {date_str} one way {cabin_query} class"
                url = f"https://www.google.com/travel/flights?q={query.replace(' ', '+')}"
                
                page.goto(url, timeout=60000)
                
                # Fecha cookies se aparecer
                try: page.get_by_role("button", name=re.compile(r"Reject|Aceitar", re.I)).first.click(timeout=3000)
                except: pass
                
                page.wait_for_load_state("networkidle")
                
                # 3. Encontrar o Card do Voo
                # Procura na lista um item que contenha o NUMERO (930) e a CIA (AA)
                flight_found = False
                target_seats = 0
                
                # Pega todos os cards de voo da tela
                cards = page.locator("li, div[role='listitem']").all()
                
                # Valida se o voo existe com 1 passageiro
                for card in cards:
                    text = card.inner_text()
                    if flight_digits in text and flight_letters in text:
                        flight_found = True
                        target_seats = 1
                        break
                
                if not flight_found:
                    results.append({**row, "Assentos": 0, "Status": "Voo não encontrado (Verifique dados)"})
                    progress_bar.progress((index + 1) / total)
                    continue

                # 4. Loop de Verificação (2 até Max)
                # Se achou com 1, vamos testar mais
                for n in range(2, max_pax_check + 1):
                    # Clica no menu de passageiros
                    btn_pax = page.locator("div[jsaction*='click']").filter(has_text=re.compile(r"^\d+$|passenger", re.I)).first
                    if not btn_pax.is_visible(): 
                        btn_pax = page.get_by_role("button", name=re.compile(r"passenger", re.I)).first
                    
                    btn_pax.click()
                    
                    # Adiciona +1 adulto
                    page.locator("button[aria-label*='Add'], button[aria-label*='Adicionar']").first.click()
                    
                    # Clica em Concluído
                    page.get_by_role("button", name=re.compile(r"Done|Concluído", re.I)).first.click()
                    
                    # Espera recarregar
                    time.sleep(1.5)
                    page.wait_for_load_state("domcontentloaded")
                    
                    # Re-verifica se o voo CONTINUA na tela
                    still_there = False
                    cards_now = page.locator("li, div[role='listitem']").all()
                    for c in cards_now:
                        if flight_digits in c.inner_text() and flight_letters in c.inner_text():
                            still_there = True
                            break
                    
                    if still_there:
                        target_seats = n
                    else:
                        # Voo sumiu, limite atingido
                        break
                
                status_msg = f"✅ {target_seats}+" if target_seats >= max_pax_check else f"⚠️ Apenas {target_seats}"
                results.append({**row, "Assentos": target_seats, "Status": status_msg})
                
            except Exception as e:
                results.append({**row, "Assentos": "Erro", "Status": str(e)})
            
            progress_bar.progress((index + 1) / total)
            
        browser.close()
        status_text.success("Varredura Completa!")
        return pd.DataFrame(results)

# --- INTERFACE (SIMPLES) ---
st.title("✈️ Scanner de Assentos Simplificado")
st.markdown("Preencha a tabela abaixo com os voos que deseja verificar.")

# 1. Configurações Globais
col_conf1, col_conf2 = st.columns(2)
with col_conf1:
    max_pax = st.slider("Verificar até quantos assentos?", 1, 9, 9)

# 2. Tabela de Entrada
default_data = [
    {"Voo": "AA 930", "Origem": "GRU", "Destino": "MIA", "Data": datetime(2026, 1, 17), "Classe": "Econômica"},
    {"Voo": "TP 104", "Origem": "CNF", "Destino": "LIS", "Data": datetime(2026, 2, 20), "Classe": "Executiva"},
]

df_input = st.data_editor(
    default_data,
    num_rows="dynamic",
    width="stretch", # Correção do aviso de depreciação
    column_config={
        "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "Classe": st.column_config.SelectboxColumn("Classe", options=["Econômica", "Executiva", "Primeira"]),
        "Voo": st.column_config.TextColumn("Voo (Cia + Num)", help="Ex: AA 930")
    }
)

# 3. Botão de Ação
if st.button("🚀 Verificar Disponibilidade Agora", type="primary", use_container_width=True):
    if len(df_input) > 0:
        df_result = get_available_seats(pd.DataFrame(df_input), max_pax)
        
        st.divider()
        st.subheader("📊 Resultados")
        
        # Estilização Condicional
        def color_seats(val):
            if isinstance(val, int) and val > 0:
                return 'background-color: #d4edda; color: black' # Verde
            return 'background-color: #f8d7da; color: black' # Vermelho

        st.dataframe(
            df_result.style.map(color_seats, subset=['Assentos']), 
            width="stretch"
        )
        
        # Download Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_result.to_excel(writer, index=False)
        
        st.download_button(
            "📥 Baixar Relatório (Excel)", 
            data=output.getvalue(), 
            file_name="assentos_voos.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("Adicione pelo menos um voo na tabela acima.")
