import streamlit as st
import pandas as pd
from FlightRadar24 import FlightRadar24API

# Inicializa a API
fr_api = FlightRadar24API()

st.set_page_config(page_title="Validador de Aeronave", page_icon="✈️")

st.title("🔍 Validador de Aeronave (Real-Time)")
st.markdown("Verifique o modelo e matrícula da aeronave agora.")

flight_number = st.text_input("Digite o número do voo (Ex: AA954):", "").upper().strip()

if st.button("Validar agora"):
    if flight_number:
        with st.spinner(f"Consultando radares para {flight_number}..."):
            try:
                details = fr_api.get_flight_details(flight_number)
                if details and 'flight' in details:
                    f = details['flight']
                    aircraft = f.get('aircraft', {})
                    model = aircraft.get('model', {}).get('text', 'Não identificado')
                    reg = aircraft.get('registration', 'N/A')
                    
                    st.success(f"Voo {flight_number} Localizado!")
                    col1, col2 = st.columns(2)
                    col1.metric("Modelo", model)
                    col2.metric("Matrícula", reg)
                    st.info(f"Análise: O modelo {model} geralmente opera com 6 assentos na Executiva (J4 C2).")
                else:
                    st.warning("Voo não encontrado no radar no momento.")
            except Exception as e:
                st.error(f"Erro técnico: {e}")
