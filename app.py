import streamlit as st
import pandas as pd
from FlightRadar24 import FlightRadar24API

# Inicializa a API (Não precisa de chave para dados básicos)
fr_api = FlightRadar24API()

st.set_page_config(page_title="Real-Time Flight Tracker", page_icon="✈️", layout="wide")

st.title("✈️ Monitor de Voos em Tempo Real")
st.markdown("Dados extraídos diretamente da malha aérea global.")

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("Busca por Voo")
    voo_input = st.text_input("Número do Voo (Ex: AA954)", "AA954").upper().replace(" ", "")
    btn_realtime = st.button("Validar em Tempo Real")

# --- LÓGICA DE BUSCA REAL ---
if btn_realtime:
    with st.spinner(f"Conectando aos radares para {voo_input}..."):
        # Busca detalhes do voo na API do FlightRadar24
        details = fr_api.get_flight_details(voo_input)
        
        if details and 'flight' in details:
            f = details['flight']
            
            # Organizando os dados reais
            status = f.get('status', {}).get('text', 'N/A')
            aeronave = f.get('aircraft', {}).get('model', {}).get('text', 'Desconhecido')
            origem = f.get('airport', {}).get('origin', {}).get('name', 'N/A')
            destino = f.get('airport', {}).get('destination', {}).get('name', 'N/A')
            
            # Layout de Exibição
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Status Atual", status)
                st.write(f"**Aeronave:** {aeronave}")
            
            with col2:
                st.write(f"**Origem:** {origem}")
                st.write(f"**Destino:** {destino}")

            # Nota sobre assentos (Buckets)
            st.info("""
                **Nota sobre Assentos:** APIs públicas de radares (gratuitas) não fornecem o inventário de vendas (Buckets J/C/Y). 
                Para validação de assentos exatos em tempo real, o sistema deve ser integrado ao GDS Amadeus ou Sabre.
            """)
            
            # Simulação técnica de Buckets baseada no modelo da aeronave detectada
            st.subheader("Estimativa de Disponibilidade Técnica")
            if "777" in aeronave:
                st.success("Configuração sugerida para este voo: Business (J4 C2) | Economy (Y9)")
            else:
                st.success("Configuração doméstica: Business (J2) | Economy (Y7)")
        else:
            st.error(f"Não foi possível encontrar dados ao vivo para o voo {voo_input} no momento.")
            st.write("Verifique se o voo está operando hoje ou tente novamente em instantes.")

# --- TABELA DE MONITORAMENTO FIXA ---
st.markdown("---")
st.subheader("Voos que você listou (Histórico de Validação)")
monitoramento = [
    {"Voo": "AA 954", "Data": "17 Jan", "Rota": "EZE-JFK", "Assentos": "6 Exec / 9 Econ"},
    {"Voo": "AA 930", "Data": "17 Jan", "Rota": "GRU-MIA", "Assentos": "Lotação Esgotada"},
    {"Voo": "AA 2131", "Data": "18 Jan", "Rota": "MIA-LAX", "Assentos": "2 First / 5 Exec"},
    {"Voo": "AA 3085", "Data": "18 Jan", "Rota": "JFK-SNA", "Assentos": "2 Exec / 7 Econ"}
]
st.table(pd.DataFrame(monitoramento))
