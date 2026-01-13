import streamlit as st
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import re
import subprocess
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime, timedelta

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Monitor Booking - Cloud Ready", page_icon="🏨", layout="wide")

# --- INSTALAÇÃO ---
def install_playwright():
    if 'playwright_installed' not in st.session_state:
        try:
            subprocess.run(["playwright", "install", "chromium"], check=True)
            st.session_state['playwright_installed'] = True
        except Exception:
            pass

install_playwright()

# --- AUXILIARES ---
def build_dated_url(original_url, checkin, checkout, guests):
    try:
        if not original_url.startswith("http"):
            original_url = "https://" + original_url

        parsed = urlparse(original_url)
        query_params = parse_qs(parsed.query)

        query_params['checkin'] = [checkin.strftime("%Y-%m-%d")]
        query_params['checkout'] = [checkout.strftime("%Y-%m-%d")]
        query_params['group_adults'] = [str(guests)]
        query_params['no_rooms'] = ['1']
        query_params['group_children'] = ['0']

        new_query = urlencode(query_params, doseq=True)
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
    except:
        return original_url

# --- CLASSE DO SCANNER (CORRIGIDA) ---
class HotelSpecificScanner:
    def __init__(self, headless=True):
        self.headless = headless
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        p = sync_playwright().start()
        
        # --- CORREÇÃO DO ERRO XSERVER ---
        # Tenta lançar com a configuração escolhida. Se falhar por falta de monitor, força Headless.
        try:
            self.browser = p.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"]
            )
        except Exception as e:
            # Se der o erro de XServer ou DISPLAY, forçamos o modo invisível
            if "Missing X server" in str(e) or "display" in str(e).lower():
                print("⚠️ Ambiente Cloud detectado. Forçando modo Headless (Invisível).")
                self.browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
                )
            else:
                raise e # Se for outro erro, deixa quebrar para sabermos o que é

        self.context = self.browser.new_context(
            viewport={"width": 1366, "height": 768}, # Tamanho fixo ajuda no headless
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

            target_url = build_dated_url(raw_url.strip(), checkin, checkout, guests)
            
            try:
                status_log.write(f"🏨 ({i+1}/{total}) Acessando hotel...")
                self.page.goto(target_url, timeout=60000)
                
                # Tenta fechar popups
                try: self.page.locator("button[aria-label*='Fechar']").click(timeout=3000)
                except: pass
                
                self.page.wait_for_load_state("domcontentloaded")
                # Scroll para garantir carregamento
                self.page.mouse.wheel(0, 1000)
                time.sleep(2)

                # 1. PEGAR NOME DO HOTEL
                try:
                    hotel_name = self.page.locator("#hp_hotel_name").inner_text().strip()
                    hotel_name = hotel_name.replace("Hotel", "").strip()
                except:
                    try: hotel_name = self.page.locator("h2").first.inner_text()
                    except: hotel_name = "Hotel Desconhecido"

                status_log.write(f"🔎 Analisando: **{hotel_name}**")

                # 2. VARRER TABELA DE QUARTOS
                found_rooms = False
                rows = self.page.locator("tr").all()
                
                # Se não achar tabela, tenta procurar blocos de quartos (layout novo)
                if len(rows) < 2:
                     rows = self.page.locator("[data-testid='room-card']").all()

                hotel_min_price = None

                for row in rows:
                    try:
                        # Tenta seletores da tabela clássica
                        name_el = row.locator(".hprt-roomtype-link")
                        if not name_el.is_visible():
                            # Tenta seletores do layout novo
                            name_el = row.locator("[data-testid='room-name']")
                        
                        if not name_el.is_visible(): continue
                        
                        room_name = name_el.inner_text().strip()
                        
                        # Preço
                        price_el = row.locator(".bui-price-display__value").first
                        if not price_el.is_visible():
                            price_el = row.locator("[data-testid='price-and-discounted-price']").first
                            
                        if not price_el.is_visible(): continue
                        price = price_el.inner_text().strip()
                        
                        # Disponibilidade
                        try:
                            avail_text = row.locator(".hprt-table-cell-room-select").inner_text()
                            if "Só mais" in avail_text:
                                avail = re.search(r"Só mais \d+", avail_text).group(0)
                            else:
                                avail = "Disponível"
                        except:
                            avail = "Disponível"

                        # Categorização
                        upper_name = room_name.upper()
                        is_suite = "SUÍTE" in upper_name or "SUITE" in upper_name or "LUXO" in upper_name or "DELUXE" in upper_name
                        category = "Suíte/Luxo" if is_suite else "Standard"
                        
                        # Limpeza preço
                        try:
                            price_clean = float(re.sub(r"[^\d,]", "", price).replace(",", "."))
                            if hotel_min_price is None or price_clean < hotel_min_price:
                                hotel_min_price = price_clean
                        except: pass

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
                
                summary.append({
                    "Hotel": hotel_name,
                    "Status": "✅ Dados extraídos" if found_rooms else "⚠️ Nenhum quarto identificado",
                    "Menor Preço": f"R$ {hotel_min_price:.2f}" if hotel_min_price else "-",
                    "Link": target_url
                })

            except Exception as e:
                summary.append({"Hotel": raw_url[:30]+"...", "Status": f"Erro: {str(e)}", "Menor Preço": "-", "Link": raw_url})

        return pd.DataFrame(summary), pd.DataFrame(all_rooms)

# --- INTERFACE ---
st.title("🏨 Monitor Booking (Nuvem/Local)")
st.markdown("Cole os links e veja a disponibilidade (Quartos e Suítes).")

with st.sidebar:
    st.header("Configuração")
    checkin = st.date_input("Check-in", datetime.today() + timedelta(days=30))
    checkout = st.date_input("Check-out", datetime.today() + timedelta(days=35))
    guests = st.number_input("Hóspedes", 1, 10, 2)
    
    # Checkbox inteligente: Avisa que não funciona na nuvem
    show_browser = st.checkbox("Ver Navegador (Só funciona no PC Local)", value=False)

urls_input = st.text_area(
    "Links dos Hotéis:",
    height=150,
    placeholder="https://www.booking.com/hotel/br/copacabana-palace.pt-br.html"
)

if st.button("🚀 Iniciar Scanner", type="primary", use_container_width=True):
    url_list = [u for u in urls_input.split('\n') if u.strip()]
    
    if not url_list:
        st.warning("Cole os links primeiro.")
    else:
        # Se estiver na nuvem, o show_browser será ignorado pelo try/catch na classe
        scanner = HotelSpecificScanner(headless=not show_browser)
        status = st.status("Iniciando varredura...", expanded=True)
        
        try:
            scanner.start()
            df_summary, df_rooms = scanner.check_hotel_list(url_list, checkin, checkout, guests, status)
            scanner.stop()
            
            status.update(label="Processo finalizado!", state="complete", expanded=False)
            
            # --- EXIBIÇÃO ---
            if not df_summary.empty:
                t1, t2, t3 = st.tabs(["Resumo", "Todos os Quartos", "Suítes"])
                
                with t1:
                    st.dataframe(df_summary, column_config={"Link": st.column_config.LinkColumn()}, use_container_width=True)
                
                with t2:
                    if not df_rooms.empty:
                        st.dataframe(df_rooms, use_container_width=True)
                    else:
                        st.info("Nenhum detalhe de quarto capturado.")
                
                with t3:
                    if not df_rooms.empty:
                        suites = df_rooms[df_rooms['Categoria'] == "Suíte/Luxo"]
                        if not suites.empty:
                            st.success(f"{len(suites)} opções de alto padrão encontradas.")
                            st.dataframe(suites, use_container_width=True)
                        else:
                            st.warning("Nenhuma suíte identificada.")
            else:
                st.error("Falha ao processar os links.")
                
        except Exception as e:
            scanner.stop()
            st.error(f"Erro crítico: {e}")
