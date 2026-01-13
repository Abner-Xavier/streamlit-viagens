import streamlit as st
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
import pandas as pd
import time
import re
import os
import subprocess

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Scanner de Assentos Google",
    page_icon="✈️",
    layout="centered"
)

# --- FUNÇÃO AUXILIAR: INSTALAÇÃO DO BROWSER ---
# Isso ajuda a garantir que funcione no Streamlit Cloud
def install_playwright_browser():
    try:
        # Verifica se a pasta do chromium existe (verificação básica)
        # Nota: Em produção real, o ideal é confiar no cache ou buildpack
        subprocess.run(["playwright", "install", "chromium"], check=True)
    except Exception as e:
        st.error(f"Erro ao instalar navegador: {e}")

# --- CLASSE DE AUTOMAÇÃO ---
class FlightScanner:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None

    def start_browser(self):
        playwright = sync_playwright().start()
        # Argumentos para tentar evitar detecção básica de bot
        self.browser = playwright.chromium.launch(
            headless=True, 
            args=["--disable-blink-features=AutomationControlled"]
        )
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        self.page = self.context.new_page()

    def close(self):
        if self.browser:
            self.browser.close()

    def check_availability(self, url, target_time, max_passengers, status_container):
        try:
            self.start_browser()
            
            status_container.write("🌎 Acessando Google Flights...")
            self.page.goto(url, timeout=60000)
            
            # Tenta fechar modal de cookies se aparecer (comum na Europa/BR)
            try:
                # Botões comuns de 'Rejeitar tudo' ou 'Aceitar'
                self.page.get_by_role("button", name=re.compile(r"Reject|Rejeitar|Accept|Aceitar", re.I)).first.click(timeout=3000)
            except:
                pass # Se não tiver cookie banner, segue a vida

            self.page.wait_for_load_state("networkidle")
            
            # Validação inicial: O voo existe com 1 passageiro?
            if not self.page.get_by_text(target_time).first.is_visible():
                return 0, "Voo não encontrado na página inicial (verifique o horário)."

            confirmed_seats = 1
            
            # Loop de incremento
            for n in range(2, max_passengers + 1):
                status_container.write(f"🔍 Testando {n} passageiros...")
                
                # 1. Abrir dropdown de passageiros
                # Usando seletores mais genéricos e robustos via ARIA ou classe
                btn_pax = self.page.locator("div[jsaction*='click']").filter(has_text=re.compile(r"\d")).first
                # Fallback se o locator acima for muito genérico, tenta achar o ícone de pessoa
                if not btn_pax.is_visible():
                     btn_pax = self.page.get_by_role("button", name=re.compile(r"passenger|passageiro", re.I)).first
                
                btn_pax.click()
                
                # 2. Clicar no botão + (Adults)
                # O Google costuma usar aria-label="Add one adult" ou similar
                btn_add = self.page.locator("div[role='button'][aria-label*='Add'], button[aria-label*='Add'], button[aria-label*='Adicionar']").first
                btn_add.click()
                
                # 3. Clicar em Done/Concluído
                btn_done = self.page.get_by_role("button", name=re.compile(r"Done|Concluído|Ok", re.I)).first
                btn_done.click()
                
                # 4. Esperar o reload da lista (loading bar ou network idle)
                # Espera 1 segundo fixo para garantir que a animação começou, depois espera network
                time.sleep(1) 
                self.page.wait_for_load_state("domcontentloaded")
                
                # 5. Verificar se o voo ainda existe
                # Usamos filter para garantir que o texto do horário está visível
                flight_visible = self.page.locator("div").filter(has_text=target_time).first.is_visible()
                
                if flight_visible:
                    confirmed_seats = n
                else:
                    status_container.warning(f"❌ Voo sumiu ao buscar {n} assentos.")
                    return confirmed_seats, "Limite atingido"
            
            return confirmed_seats, "Capacidade máxima verificada"

        except PlaywrightTimeout:
            return -1, "Tempo limite excedido (Internet lenta ou bloqueio)."
        except Exception as e:
            return -1, f"Erro técnico: {str(e)}"
        finally:
            self.close()

# --- INTERFACE DO USUÁRIO ---
st.title("✈️ Verificador de Disponibilidade")
st.markdown("Automator para verificar 'assentos fantasmas' ou disponibilidade real.")

with st.expander("ℹ️ Como usar", expanded=False):
    st.write("""
    1. Faça
