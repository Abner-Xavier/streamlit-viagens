import streamlit as st
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import subprocess
import io
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Scanner Debugger", page_icon="🕵️", layout="wide")

# --- INSTALAÇÃO ---
def install_playwright():
    if 'playwright_installed' not in st.session_state:
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True)
            st.session_state['playwright_installed'] = True
        except Exception:
            pass

install_playwright()

# --- MOTOR DE BUSCA (COM SNAPSHOT) ---
def get_available_seats(flights_df, max_pax_check):
    results = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, # Mantém invisível para não dar erro no servidor
            args=[
                "--disable-blink-features=AutomationControlled", 
                "--no-sandbox", 
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )
        # Contexto com tamanho de tela grande para garantir que elementos carreguem
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        total = len(flights_df)
        
        for index, row in flights_df.iterrows():
            row_result = row.to_dict()
            row_result["Debug_Image"] = None # Coluna para guardar a foto do erro
            
            try:
                # Dados
                flight_raw = str(row['Voo']).upper().strip()
                # Tenta pegar apenas numeros (ex: 930)
                flight_digits = "".join(re.findall(r"\d+", flight_raw))
                
                origin, dest = row['Origem'], row['Destino']
                date_str = row['Data'].strftime("%Y-%m-%d")
                
                cabin_map = {"Econômica": "economy", "Executiva": "business", "Primeira": "first"}
                cabin_query = cabin_map.get(row['Classe'], "economy")
                
                status_text.markdown(f"📸 Analisando **{flight_raw}** ({origin}-{dest})...")
                
                # URL
                query = f"Flights from {origin} to {dest} on {date_str} one way {cabin_query} class"
                url = f"https://www.google.com/travel/flights?q={query.replace(' ', '+')}"
                
                page.goto(url, timeout=45000)
                
                # Tenta limpar popups
                try: page.get_by_role("button", name=re.compile(r"Reject|Aceitar|Concordo", re.I)).first.click(timeout=3000)
                except: pass
                
                # Espera extra para renderização visual
                page.wait_for_load_state("networkidle")
                time.sleep(2) 
                
                # --- ESTRATÉGIA DE BUSCA ---
                cards = page.locator("li, div[role='listitem']").all()
                flight_found = False
                target_seats = 0
                
                # 1. Busca Estrita (AA + 930)
                for card in cards:
                    txt = card.inner_text()
                    if flight_digits in txt:
                        # Achamos o cartão que tem o número "930"
                        flight_found = True
                        target_seats = 1 # Começa com 1 confirmado
                        break
                
                if not flight_found:
                    # SE DER ZERO: TIRA FOTO!
                    row_result["Assentos"] = 0
                    row_result["Status"] = "Voo não encontrado na lista"
                    row_result["Debug_Image"] = page.screenshot() # Salva o print
                    results.append(row_result)
                    continue

                # 2. Loop de Passageiros (se achou o voo)
                for n in range(2, max_pax_check + 1):
                    # Abre menu
                    btn_pax = page.locator("div[jsaction*='click']").filter(has_text=re.compile(r"^\d+$|passenger", re.I)).first
                    if not btn_pax.is_visible(): 
                        # Fallback
                        btn_pax = page.get_by_role("button", name=re.compile(r"passenger", re.I)).first
                    
                    if btn_pax.is_visible():
                        btn_pax.click()
                        time.sleep(0.5)
                        
                        # Add pax
                        page.locator("button[aria-label*='Add'], button[aria-label*='Adicionar']").first.click()
                        
                        # Done
                        page.get_by_role("button", name=re.compile(r"Done|Concluído", re.I)).first.click()
                        
                        time.sleep(1.5)
                        page.wait_for_load_state("domcontentloaded")
                        
                        # Re-verifica se o numero "930" ainda está na tela
                        still_visible = False
                        new_cards = page.locator("li, div[role='listitem']").all()
                        for c in new_cards:
                            if flight_digits in c.inner_text():
                                still_visible = True
                                break
                        
                        if still_visible:
                            target_seats = n
                        else:
                            break # Limite atingido
                
                row_result["Assentos"] = target_seats
                row_result["Status"] = "Disponível" if target_seats > 0 else "Indisponível"
                
                # Se mesmo depois de tudo deu 0 ou erro, tira foto
                if target_seats == 0:
                    row_result["Debug_Image"] = page.screenshot()

                results.append(row_result)

            except Exception as e:
                # Erro técnico? Tira foto também
                try: img = page.screenshot()
                except: img = None
                row_result["Assentos"] = 0
                row_result["Status"] = f"Erro: {str(e)}"
                row_result["Debug_Image"] = img
                results.append(row_result)
            
            progress_bar.progress((index + 1) / total)

        browser.close()
        status_text.success("Processado!")
        return results

# --- INTERFACE ---
st.title("🕵️ Scanner com Diagnóstico (Debug)")
st.markdown("Se o resultado for 0, mostrarei uma **foto** do que o robô viu.")

# Inputs
c1, c2 = st.columns(2)
max_pax = c1.slider("Max Passageiros", 1, 9, 9)

# Tabela Input
default_data = [{"Voo": "AA 930", "Origem": "GRU", "Destino": "MIA", "Data": datetime(2026, 1, 17), "Classe": "Econômica"}]
df_input = st.data_editor(default_data, num_rows="dynamic", width="stretch", column_config={
    "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
    "Classe": st.column_config.SelectboxColumn("Classe", options=["Econômica", "Executiva", "Primeira"])
})

if st.button("🚀 Rodar Scanner", type="primary", use_container_width=True):
    if len(df_input) > 0:
        results_data = get_available_seats(pd.DataFrame(df_input), max_pax)
        
        st.divider()
        st.subheader("Resultados")
        
        for res in results_data:
            # Layout do card de resultado
            with st.container(border=True):
                cols = st.columns([1, 1, 2])
                cols[0].metric("Voo", res['Voo'])
                
                color = "normal" if res['Assentos'] > 0 else "off"
                cols[1].metric("Assentos", res['Assentos'], delta=res['Status'], delta_color=color)
                
                # SE TIVER IMAGEM DE DEBUG (ERRO/ZERO), MOSTRA
                if res['Debug_Image']:
                    st.warning(f"⚠️ Alerta: O robô não encontrou assentos. Veja o que ele viu na tela para o voo {res['Voo']}:")
                    st.image(res['Debug_Image'], caption="Visão do Robô (Screenshot)", width=700)
                else:
                    st.success("Leitura realizada com sucesso.")

    else:
        st.error("Adicione voos.")
