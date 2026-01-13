import streamlit as st
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import subprocess
import io
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Scanner Visual (Horário)", page_icon="👁️", layout="wide")

# --- INSTALAÇÃO ---
def install_playwright():
    if 'playwright_installed' not in st.session_state:
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True)
            st.session_state['playwright_installed'] = True
        except Exception:
            pass

install_playwright()

# --- MOTOR DE BUSCA (POR HORÁRIO) ---
def scan_visual(df_input, max_pax):
    results = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        page = browser.new_page(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        status = st.empty()
        prog = st.progress(0)
        
        for i, row in df_input.iterrows():
            origin, dest = row['Origem'].upper(), row['Destino'].upper()
            date_str = row['Data'].strftime("%Y-%m-%d")
            # Hora Alvo (Ex: "11:30 PM")
            target_time = str(row['Horário']).strip()
            
            # Mapeamento de classe
            cabin_map = {"Econômica": "economy", "Executiva": "business", "Primeira": "first"}
            cabin = cabin_map.get(row['Classe'], "economy")
            
            status.info(f"🔎 Buscando voo das **{target_time}** ({origin}->{dest})...")
            
            # URL
            query = f"Flights from {origin} to {dest} on {date_str} one way {cabin} class"
            url = f"https://www.google.com/travel/flights?q={query.replace(' ', '+')}"
            
            try:
                page.goto(url, timeout=45000)
                try: page.get_by_role("button", name=re.compile(r"Reject|Aceitar", re.I)).first.click(timeout=3000)
                except: pass
                page.wait_for_load_state("networkidle")
                
                # --- LÓGICA DE IDENTIFICAÇÃO VISUAL ---
                # Pega todos os cards de voo
                cards = page.locator("li, div[role='listitem']").all()
                found_card = None
                
                # Procura qual card tem o horário específico
                for card in cards:
                    text = card.inner_text()
                    # Verifica se "11:30 PM" está no texto do cartão
                    if target_time in text:
                        found_card = card
                        break
                
                if not found_card:
                    # Se não achou pelo horário exato, tira print
                    results.append({
                        "Rota": f"{origin}-{dest}",
                        "Horário": target_time,
                        "Assentos": 0,
                        "Status": "Voo não encontrado (Horário não bate)",
                        "Print": page.screenshot()
                    })
                    continue

                # Se achou o cartão, começa o teste de assentos
                available = 1
                
                for n in range(2, max_pax + 1):
                    # Clica no seletor de passageiros
                    btn_pax = page.locator("div[jsaction*='click']").filter(has_text=re.compile(r"^\d+$|passenger", re.I)).first
                    if not btn_pax.is_visible():
                         btn_pax = page.get_by_role("button", name=re.compile(r"passenger", re.I)).first
                    
                    if btn_pax.is_visible():
                        btn_pax.click()
                        # Adiciona passageiro
                        page.locator("button[aria-label*='Add'], button[aria-label*='Adicionar']").first.click()
                        # Fecha menu
                        page.get_by_role("button", name=re.compile(r"Done|Concluído", re.I)).first.click()
                        
                        time.sleep(1.5) # Aguarda refresh
                        
                        # Re-verifica se o cartão com aquele horário AINDA EXISTE
                        # O Google pode remover o voo ou mudar o preço/posição
                        still_exists = False
                        new_cards = page.locator("li, div[role='listitem']").all()
                        for c in new_cards:
                            if target_time in c.inner_text():
                                still_exists = True
                                break
                        
                        if still_exists:
                            available = n
                        else:
                            break # Voo sumiu
                    else:
                        break

                results.append({
                    "Rota": f"{origin}-{dest}",
                    "Horário": target_time,
                    "Assentos": available,
                    "Status": "Disponível" if available > 0 else "Indisponível",
                    "Print": None
                })

            except Exception as e:
                results.append({
                    "Rota": f"{origin}-{dest}",
                    "Horário": target_time,
                    "Assentos": 0,
                    "Status": f"Erro: {str(e)}",
                    "Print": page.screenshot()
                })
                
            prog.progress((i+1)/len(df_input))
            
        browser.close()
        status.success("Concluído!")
        return results

# --- INTERFACE ---
st.title("👁️ Scanner Visual (Busca por Horário)")
st.markdown("Use o **Horário de Partida** exatamente como aparece no Google (ex: `11:30 PM`) para identificar o voo.")

c1, c2 = st.columns(2)
max_pax = c1.slider("Max Passageiros", 1, 9, 9)

# Tabela de Entrada
default = [{"Origem": "GRU", "Destino": "MIA", "Data": datetime(2026, 1, 17), "Horário": "11:30 PM", "Classe": "Econômica"}]
df = st.data_editor(default, num_rows="dynamic", width="stretch", column_config={
    "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
    "Horário": st.column_config.TextColumn(help="Copie do site, ex: 11:30 PM ou 23:30"),
    "Classe": st.column_config.SelectboxColumn(options=["Econômica", "Executiva", "Primeira"])
})

if st.button("🚀 Verificar Assentos", type="primary", use_container_width=True):
    if len(df) > 0:
        data = scan_visual(pd.DataFrame(df), max_pax)
        
        st.divider()
        for res in data:
            with st.container(border=True):
                col1, col2, col3 = st.columns([2, 1, 2])
                col1.metric("Voo", f"{res['Rota']} ({res['Horário']})")
                
                color = "normal" if res['Assentos'] > 0 else "off"
                col2.metric("Assentos", res['Assentos'], delta=res['Status'], delta_color=color)
                
                if res['Assentos'] == 0 and res['Print']:
                    st.image(res['Print'], caption="Tela do Erro", width=500)
    else:
        st.warning("Preencha a tabela.")
