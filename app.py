import streamlit as st
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import subprocess
import io
from datetime import datetime

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Scanner Geral (Incognito)", page_icon="🕵️", layout="wide")

# --- INSTALAÇÃO ---
def install_playwright():
    if 'playwright_installed' not in st.session_state:
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True)
            st.session_state['playwright_installed'] = True
        except Exception:
            pass

install_playwright()

# --- MOTOR DE EXTRAÇÃO (MODO ANÔNIMO) ---
def scrape_all_flights(origin, dest, date_obj, cabin_class):
    data = []
    
    with sync_playwright() as p:
        # Browser Invisível com Flag Incognito Explícita
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--incognito",  # <--- FORÇA MODO ANÔNIMO
                "--disable-blink-features=AutomationControlled", 
                "--no-sandbox"
            ]
        )
        
        # Cria um contexto isolado (já atua como aba anônima por padrão)
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        
        # Montagem da URL
        date_str = date_obj.strftime("%Y-%m-%d")
        cabin_map = {"Econômica": "economy", "Executiva": "business", "Primeira": "first"}
        cabin = cabin_map.get(cabin_class, "economy")
        
        query = f"Flights from {origin} to {dest} on {date_str} one way {cabin} class"
        url = f"https://www.google.com/travel/flights?q={query.replace(' ', '+')}"
        
        try:
            st.toast("Iniciando sessão anônima...", icon="🕵️")
            page.goto(url, timeout=60000)
            
            # Limpa Cookies (Mesmo em anônimo, o Google pede consentimento na Europa/BR)
            try: page.get_by_role("button", name=re.compile(r"Reject|Aceitar", re.I)).first.click(timeout=3000)
            except: pass
            
            page.wait_for_load_state("networkidle")
            
            # --- TENTA EXPANDIR A LISTA ---
            try:
                # Tenta clicar em "Ver mais voos" se estiver escondido
                btn_more = page.locator("button").filter(has_text="View more flights").or_(page.locator("button").filter(has_text="Ver mais voos"))
                if btn_more.is_visible():
                    btn_more.click()
                    time.sleep(2)
            except:
                pass
            
            # Rola a página para garantir carregamento (Lazy Loading)
            page.mouse.wheel(0, 3000)
            time.sleep(1.5)
            
            # --- COLETA DE DADOS ---
            cards = page.locator("li, div[role='listitem']").all()
            
            for card in cards:
                text = card.inner_text()
                
                # Filtro rápido para garantir que é um cartão de voo
                if not re.search(r"\d{1,2}:\d{2}", text):
                    continue
                
                # 1. Horários
                times = re.findall(r"(\d{1,2}:\d{2}\s?[AP]?M?)", text)
                if len(times) < 2: continue
                
                # 2. Preço
                price_match = re.search(r"((?:R\$|\$|€|£)\s?[\d,.]+)", text)
                price = price_match.group(1) if price_match else "N/A"
                
                # 3. Duração
                duration_match = re.search(r"(\d+\s?hr\s?\d*\s?min|\d+\s?h\s?\d*\s?m)", text)
                duration = duration_match.group(1) if duration_match else ""
                
                # 4. Paradas
                stops = "Direto"
                if "1 stop" in text or "1 parada" in text: stops = "1 Parada"
                elif "2 stops" in text or "2 paradas" in text: stops = "+2 Paradas"
                
                # 5. Cia Aérea (Heurística simples baseada na quebra de linha comum do Google)
                # O Google geralmente coloca a Cia logo após o horário ou duração.
                # Como é difícil extrair exato sem classes CSS dinâmicas, salvamos o texto bruto limpo.
                
                data.append({
                    "Partida": times[0],
                    "Chegada": times[1] if len(times) > 1 else "?",
                    "Duração": duration,
                    "Preço": price,
                    "Paradas": stops,
                    # Removemos quebras de linha para o Excel ficar limpo
                    "Resumo do Cartão": text.replace("\n", " | ")[:150] 
                })
                
        except Exception as e:
            st.error(f"Erro na extração: {e}")
            
        browser.close()
        return pd.DataFrame(data)

# --- INTERFACE ---
st.title("🕵️ Scanner de Mercado (Modo Anônimo)")
st.markdown("Extrai todos os voos disponíveis garantindo uma sessão limpa (sem cookies/histórico).")

with st.sidebar:
    st.header("Dados da Viagem")
    origin = st.text_input("Origem", "GRU", max_chars=3).upper()
    dest = st.text_input("Destino", "MIA", max_chars=3).upper()
    date_val = st.date_input("Data", min_value=datetime.today())
    cabin = st.selectbox("Classe", ["Econômica", "Executiva", "Primeira"])

if st.button("🚀 Pesquisar (Sessão Limpa)", type="primary", use_container_width=True):
    if origin and dest:
        with st.status("Abrindo navegador anônimo...", expanded=True) as status:
            df_result = scrape_all_flights(origin, dest, date_val, cabin)
            
            if not df_result.empty:
                status.write(f"✅ Sucesso! {len(df_result)} voos encontrados.")
                status.update(label="Concluído!", state="complete", expanded=False)
                
                st.divider()
                st.subheader(f"Voos: {origin} ➔ {dest} ({date_val})")
                
                # Tabela Visual
                st.dataframe(df_result, use_container_width=True)
                
                # Excel Download
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_result.to_excel(writer, index=False)
                
                file_name = f"voos_{origin}_{dest}_{date_val}_anonimo.xlsx"
                
                st.download_button(
                    label="📥 Baixar Excel (.xlsx)",
                    data=output.getvalue(),
                    file_name=file_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                status.update(label="Falha na busca", state="error")
                st.warning("Nenhum voo encontrado. O Google pode ter pedido CAPTCHA.")
    else:
        st.warning("Preencha Origem e Destino.")
