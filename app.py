import streamlit as st
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import subprocess
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime, timedelta

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Monitor de Hotéis Específicos", page_icon="🏨", layout="wide")

# --- INSTALAÇÃO ---
def install_playwright():
    if 'playwright_installed' not in st.session_state:
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True)
            st.session_state['playwright_installed'] = True
        except Exception:
            pass

install_playwright()

# --- FUNÇÃO: AJUSTAR URL COM DATAS ---
def build_dated_url(original_url, checkin, checkout, guests):
    """
    Pega o link bruto do hotel e injeta as datas selecionadas pelo usuário.
    Isso garante que o Booking mostre o preço para a data certa.
    """
    try:
        # Garante que a URL tenha esquema (http)
        if not original_url.startswith("http"):
            original_url = "https://" + original_url

        parsed = urlparse(original_url)
        query_params = parse_qs(parsed.query)

        # Atualiza/Força os parâmetros de busca
        query_params['checkin'] = [checkin.strftime("%Y-%m-%d")]
        query_params['checkout'] = [checkout.strftime("%Y-%m-%d")]
        query_params['group_adults'] = [str(guests)]
        query_params['no_rooms'] = ['1']
        query_params['group_children'] = ['0']

        # Reconstrói a URL
        new_query = urlencode(query_params, doseq=True)
        new_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
        return new_url
    except:
        return original_url

# --- CLASSE DO SCANNER ---
class HotelSpecificScanner:
    def __init__(self, headless=False):
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        p = sync_playwright().start()
        self.browser = p.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"]
        )
        self.context = self.browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.page = self.context.new_page()

    def stop(self):
        if self.browser: self.browser.close()

    def check_hotel_list(self, url_list, checkin, checkout, guests, status_log):
        all_rooms = []
        summary = []

        total = len(url_list)

        for i, raw_url in enumerate(url_list):
            if not raw_url.strip(): continue

            # Monta URL com a data correta
            target_url = build_dated_url(raw_url.strip(), checkin, checkout, guests)
            
            try:
                status_log.write(f"🏨 ({i+1}/{total}) Acessando hotel...")
                self.page.goto(target_url, timeout=60000)
                
                # Tenta fechar popups
                try: self.page.locator("button[aria-label*='Fechar']").click(timeout=3000)
                except: pass
                
                self.page.wait_for_load_state("domcontentloaded")
                time.sleep(2) # Espera tabela carregar

                # 1. PEGAR NOME DO HOTEL
                try:
                    hotel_name = self.page.locator("#hp_hotel_name").inner_text().strip()
                    # Remove a palavra "Hotel" ou estrelas se vier junto
                    hotel_name = hotel_name.replace("Hotel", "").strip()
                except:
                    # Fallback se o ID mudar
                    try: hotel_name = self.page.locator("h2").first.inner_text()
                    except: hotel_name = "Hotel Desconhecido"

                status_log.write(f"🔎 Analisando quartos de: **{hotel_name}**")

                # 2. VARRER TABELA DE QUARTOS
                # O Booking usa uma tabela com classe 'hprt-table' ou blocos de quartos
                found_rooms = False
                
                # Tenta linhas da tabela
                rows = self.page.locator("tr").all()
                
                hotel_min_price = None

                for row in rows:
                    try:
                        # Verifica se é uma linha de quarto (tem nome e preço)
                        # Nome do quarto
                        name_el = row.locator(".hprt-roomtype-link")
                        if not name_el.is_visible(): continue
                        
                        room_name = name_el.inner_text().strip()
                        
                        # Preço
                        price_el = row.locator(".bui-price-display__value").first
                        if not price_el.is_visible(): continue
                        price = price_el.inner_text().strip()
                        
                        # Disponibilidade (Ex: "Só mais 1 quarto")
                        try:
                            avail_text = row.locator(".hprt-table-cell-room-select").inner_text()
                            if "Só mais" in avail_text:
                                avail = re.search(r"Só mais \d+", avail_text).group(0)
                            else:
                                avail = "Disponível"
                        except:
                            avail = "Disponível"

                        # Define Categoria (Lógica Simples)
                        is_suite = "SUÍTE" in room_name.upper() or "SUITE" in room_name.upper() or "LUXO" in room_name.upper()
                        category = "Suíte/Luxo" if is_suite else "Standard"
                        
                        # Limpeza do preço para ordenar depois
                        price_clean = float(re.sub(r"[^\d,]", "", price).replace(",", "."))
                        if hotel_min_price is None or price_clean < hotel_min_price:
                            hotel_min_price = price_clean

                        all_rooms.append({
                            "Hotel": hotel_name,
                            "Quarto": room_name,
                            "Categoria": category,
                            "Preço": price,
                            "Disponibilidade": avail,
                            "Link": target_url
                        })
                        found_rooms = True
                        
                    except:
                        continue
                
                # Resumo do Hotel
                summary.append({
                    "Hotel": hotel_name,
                    "Status": "Vagas Encontradas" if found_rooms else "Esgotado / Erro",
                    "Menor Preço": f"R$ {hotel_min_price:.2f}" if hotel_min_price else "-",
                    "Link": target_url
                })

            except Exception as e:
                summary.append({"Hotel": raw_url[:30]+"...", "Status": f"Erro: {str(e)}", "Menor Preço": "-", "Link": raw_url})

        return pd.DataFrame(summary), pd.DataFrame(all_rooms)

# --- INTERFACE ---
st.title("🏨 Monitor de Hotéis Específicos")
st.markdown("Cole os links do Booking.com e veja a disponibilidade exata para suas datas.")

# Sidebar
with st.sidebar:
    st.header("Datas da Viagem")
    checkin = st.date_input("Check-in", datetime.today() + timedelta(days=30))
    checkout = st.date_input("Check-out", datetime.today() + timedelta(days=35))
    guests = st.number_input("Hóspedes", 1, 10, 2)
    show_browser = st.checkbox("Ver Navegador", value=True, help="Útil para passar por Captchas manuais.")

# Área de Input de URLs
urls_input = st.text_area(
    "Cole os links dos hotéis (um por linha):",
    height=150,
    placeholder="https://www.booking.com/hotel/br/copacabana-palace.pt-br.html\nhttps://www.booking.com/hotel/br/fasano-rio-de-janeiro.pt-br.html",
    help="Cole o link da página principal do hotel. Não se preocupe com as datas no link, o robô vai ajustar."
)

if st.button("🚀 Verificar Disponibilidade", type="primary", use_container_width=True):
    url_list = [u for u in urls_input.split('\n') if u.strip()]
    
    if not url_list:
        st.warning("Cole pelo menos um link.")
    else:
        scanner = HotelSpecificScanner(headless=not show_browser)
        status = st.status("Iniciando varredura...", expanded=True)
        
        try:
            scanner.start()
            df_summary, df_rooms = scanner.check_hotel_list(url_list, checkin, checkout, guests, status)
            scanner.stop()
            
            status.update(label="Concluído!", state="complete", expanded=False)
            
            # --- RESULTADOS ---
            tab1, tab2, tab3 = st.tabs(["📊 Resumo", "🛏️ Todos os Quartos", "💎 Apenas Suítes"])
            
            with tab1:
                st.dataframe(
                    df_summary, 
                    column_config={"Link": st.column_config.LinkColumn("Ver no Booking")},
                    use_container_width=True
                )
                
            with tab2:
                if not df_rooms.empty:
                    st.dataframe(df_rooms, use_container_width=True)
                else:
                    st.info("Nenhum quarto encontrado para estas datas.")
                    
            with tab3:
                if not df_rooms.empty:
                    # Filtra apenas suítes
                    suites = df_rooms[df_rooms['Categoria'] == "Suíte/Luxo"]
                    if not suites.empty:
                        st.success(f"{len(suites)} Suítes encontradas!")
                        st.dataframe(suites, use_container_width=True)
                    else:
                        st.warning("Nenhum quarto identificado como 'Suíte' ou 'Luxo' disponível.")
                else:
                    st.info("Sem dados.")
                    
        except Exception as e:
            scanner.stop()
            st.error(f"Erro no processo: {e}")
