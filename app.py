import streamlit as st
from playwright.sync_api import sync_playwright
import re
import pandas as pd
import time

# --- CONFIGURAÇÃO DA INTERFACE ---
st.set_page_config(page_title="Scanner de Assentos Google", page_icon="✈️")

st.title("✈️ Verificador de Disponibilidade Google Flights")
st.markdown("""
Esta ferramenta testa a disponibilidade de assentos adicionando passageiros um a um 
até que o voo específico desapareça da lista.
""")

# --- INPUTS DO USUÁRIO ---
with st.container():
    url_input = st.text_input("Cole a URL da busca do Google Flights:", placeholder="https://www.google.com/travel/flights/search?...")
    
    col_input1, col_input2 = st.columns(2)
    with col_input1:
        voo_hora = st.text_input("Horário exato do voo (ex: 8:45 PM):", "8:45 PM")
    with col_input2:
        max_passageiros = st.slider("Testar até quantos passageiros?", 1, 9, 9)

btn_executar = st.button("🚀 Iniciar Verificação", use_container_width=True)

# --- FUNÇÃO DE AUTOMAÇÃO ---
def verificar_disponibilidade(url, horario, limite):
    with sync_playwright() as p:
        # Launching browser
        browser = p.chromium.launch(headless=True) # Mude para False se quiser ver o robô agindo
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
        page = context.new_page()
        
        try:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            status_text.text("Conectando ao Google Flights...")
            page.goto(url, timeout=60000)
            page.wait_for_load_state("networkidle")
            
            assentos_confirmados = 0
            
            for n in range(1, limite + 1):
                # Atualiza interface
                progresso = n / limite
                progress_bar.progress(progresso)
                status_text.text(f"Testando disponibilidade para {n} passageiro(s)...")

                if n > 1:
                    # Clica para abrir o seletor de passageiros
                    page.get_by_role("button", name=re.compile(r"passenger|passageiro", re.I)).click()
                    # Clica no botão + (Add adult)
                    page.get_by_role("button", name=re.compile(r"Add adult|Adicionar adulto", re.I)).click()
                    # Clica em Concluído
                    page.get_by_role("button", name=re.compile(r"Done|Concluído", re.I)).click()
                    
                    # Espera o Google atualizar a lista
                    time.sleep(2.5) 

                # Verifica se o voo com o horário alvo ainda está visível
                voo_visivel = page.get_by_text(horario).is_visible()
                
                if voo_visivel:
                    assentos_confirmados = n
                else:
                    status_text.error(f"O voo das {horario} não suporta {n} passageiros.")
                    break
            
            browser.close()
            return assentos_confirmados

        except Exception as e:
            browser.close()
            return f"Erro: {str(e)}"

# --- EXIBIÇÃO DO RESULTADO ---
if btn_executar:
    if not url_input:
        st.warning("⚠️ Por favor, cole a URL do Google Flights.")
    else:
        resultado = verificar_disponibilidade(url_input, voo_hora, max_passageiros)
        
        if isinstance(resultado, int):
            st.balloons()
            st.divider()
            
            # Criando métricas visuais
            c1, c2 = st.columns(2)
            c1.metric("Voo Monitorado", voo_hora)
            
            if resultado >= max_passageiros:
                c2.metric("Assentos Encontrados", f"{resultado}+", delta="Capacidade máxima testada")
            else:
                c2.metric("Assentos Encontrados", resultado, delta="- Limite atingido", delta_color="inverse")
            
            # Tabela de resumo
            dados = {
                "Horário do Voo": [voo_hora],
                "Assentos Disponíveis": [resultado],
                "Status": ["Confirmado" if resultado > 0 else "Indisponível"]
            }
            st.table(pd.DataFrame(dados))
        else:
            st.error(resultado)
