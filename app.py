import streamlit as st
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import subprocess
import io
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Scanner de Rota (Sem Voo)", page_icon="✈️", layout="wide")

# --- INSTALAÇÃO ---
def install_playwright():
    if 'playwright_installed' not in st.session_state:
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True)
            st.session_state['playwright_installed'] = True
        except Exception:
            pass

install_playwright()

# --- MOTOR DE BUSCA (FOCADO NA ROTA) ---
def scan_routes(df_input, max_pax):
    results = []
    
    with sync_playwright() as p:
        # Modo invisível (Headless) para servidor
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"]
        )
        # Contexto mobile/tablet as vezes carrega mais rápido, mas vamos usar desktop padrão
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768}
        )
        
        prog_bar = st.progress(0)
        status = st.empty()
        
        for i, row in df_input.iterrows():
            # Prepara dados
            origin, dest = row['Origem'].upper(), row['Destino'].upper()
            date_str = row['Data'].strftime("%Y-%m-%d")
            
            # Mapeamento de classe
            cabin_map = {"Econômica": "economy", "Executiva": "business", "Primeira": "first"}
            cabin = cabin_map.get(row['Classe'], "economy")
            
            status.markdown(f"🔎 Analisando rota **{origin} ➔ {dest}** em {date_str}...")
            
            # URL de busca
            query = f"Flights from {origin} to {dest} on {date_str} one way {cabin} class"
            url = f"https://www.google.com/travel/flights?q={query.replace(' ', '+')}"
            
            try:
                page.goto(url, timeout=45000)
                
                # Fecha popups
                try: page.get_by_role("button", name=re.compile(r"Reject|Aceitar", re.I)).first.click(timeout=3000)
                except: pass
                
                page.wait_for_load_state("networkidle")
                
                # --- AQUI ESTÁ A MUDANÇA: PEGA O PRIMEIRO VOO ---
                # Não procuramos por "AA 930". Pegamos o primeiro card da lista.
                first_card = page.locator("li, div[role='listitem']").first
                
                if not first_card.is_visible():
                    results.append({
                        "Rota": f"{origin}-{dest}",
                        "Data": row['Data'],
                        "Assentos": 0,
                        "Detalhe": "Nenhum voo encontrado nesta data",
                        "Print": page.screenshot()
                    })
                    continue

                # Extrai informações do voo encontrado para mostrar ao usuário
                try:
                    # Tenta ler o horário e a cia aérea para confirmar qual voo pegou
                    card_text = first_card.inner_text().split('\n')
                    flight_info = f"{card_text[0]} - {card_text[1]}" # Ex: 8:45 PM - American
                except:
                    flight_info = "Primeiro voo da lista"

                # TESTE DE CAPACIDADE
                available = 1
                
                for n in range(2, max_pax + 1):
                    # Menu Pax
                    btn_pax = page.locator("div[jsaction*='click']").filter(has_text=re.compile(r"^\d+$|passenger", re.I)).first
                    if not btn_pax.is_visible(): 
                         btn_pax = page.get_by_role("button", name=re.compile(r"passenger", re.I)).first
                    
                    if btn_pax.is_visible():
                        btn_pax.click()
                        # Add
                        page.locator("button[aria-label*='Add'], button[aria-label*='Adicionar']").first.click()
                        # Done
                        page.get_by_role("button", name=re.compile(r"Done|Concluído", re.I)).first.click()
                        
                        time.sleep(1.2) # Breve pausa para reload
                        
                        # Verifica se o PRIMEIRO card ainda existe/é visível
                        # Nota: Se o voo lotar, ele some ou muda de posição. 
                        # Assumimos que se o primeiro card mudar drasticamente ou sumir, atingiu o limite.
                        # Mas o Google costuma apenas remover o voo da lista se não tiver vaga.
                        
                        if page.locator("li, div[role='listitem']").first.is_visible():
                            available = n
                        else:
                            break
                    else:
                        break
                
                results.append({
                    "Rota": f"{origin}-{dest}",
                    "Data": row['Data'],
                    "Assentos": available,
                    "Detalhe": f"Voo detectado: {flight_info}",
                    "Print": None
                })
                
            except Exception as e:
                results.append({
                    "Rota": f"{origin}-{dest}",
                    "Data": row['Data'],
                    "Assentos": 0,
                    "Detalhe": f"Erro: {str(e)}",
                    "Print": page.screenshot()
                })
            
            prog_bar.progress((i + 1) / len(df_input))

        browser.close()
        status.success("Finalizado!")
        return results

# --- INTERFACE ---
st.title("✈️ Scanner de Disponibilidade (Por Rota)")
st.markdown("Verifica a disponibilidade do **primeiro/melhor voo** disponível na rota.")

c1, c2 = st.columns(2)
max_pax = c1.slider("Max Passageiros", 1, 9, 9)

# Tabela simplificada (Sem número de voo)
default = [{"Origem": "GRU", "Destino": "MIA", "Data": datetime(2026, 1, 17), "Classe": "Econômica"}]
df = st.data_editor(default, num_rows="dynamic", width="stretch", column_config={
    "Data": st.column_config.DateColumn(format="DD/MM/YYYY"),
    "Classe": st.column_config.SelectboxColumn(options=["Econômica", "Executiva", "Primeira"])
})

if st.button("🚀 Verificar Disponibilidade", type="primary", use_container_width=True):
    if len(df) > 0:
        data = scan_routes(pd.DataFrame(df), max_pax)
        
        st.divider()
        st.subheader("Resultados")
        
        for res in data:
            with st.container(border=True):
                cols = st.columns([2, 1, 3])
                cols[0].metric(res['Rota'], res['Data'].strftime('%d/%m/%Y'))
                
                cor = "normal" if res['Assentos'] > 0 else "off"
                cols[1].metric("Assentos", res['Assentos'], delta_color=cor)
                
                cols[2].caption(f"ℹ️ {res['Detalhe']}")
                
                if res['Assentos'] == 0 and res['Print']:
                    st.image(res['Print'], caption="Erro na tela", width=500)
    else:
        st.warning("Preencha a tabela.")
