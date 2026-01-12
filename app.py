import streamlit as st
import pandas as pd
from FlightRadar24 import FlightRadar24API

# Inicializa a API
fr_api = FlightRadar24API()

st.set_page_config(page_title="Validador de Aeronave", page_icon="✈️")

st.title("🔍 Validador de Aeronave (Real-Time)")
st.markdown("Verifique o modelo e matrícula da aeronave agora.")

# Campo de entrada focado no número do voo
flight_number = st.text_input("Digite o número do voo (Ex: AA954, AA930):", "").upper().strip()

if st.button("Validar agora"):
    if flight_number:
        with st.spinner(f"Consultando radares para {flight_number}..."):
            try:
                # Busca detalhes do voo
                details = fr_api.get_flight_details(flight_number)
                
                if details and 'flight' in details:
                    f = details['flight']
                    aircraft = f.get('aircraft', {})
                    model = aircraft.get('model', {}).get('text', 'Não identificado')
                    registration = aircraft.get('registration', 'N/A')
                    
                    st.success(f"Voo {flight_number} Localizado!")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Modelo da Aeronave", model)
                    with col2:
                        st.metric("Matrícula (Tail Number)", registration)
                    
                    st.info(f"**Análise técnica:** Para o modelo {model}, a configuração de assentos geralmente segue o padrão da American Airlines (Ex: 6 Executiva / 9 Econômica).")
                else:
                    st.warning("Voo não encontrado no radar no momento. Tente um voo que esteja no ar agora.")
            except Exception as e:
                st.error(f"Erro na conexão com os dados: {e}")
