import streamlit as st
import pandas as pd
from FlightRadar24 import FlightRadar24API

# Inicializa o acesso aos dados reais
fr_api = FlightRadar24API()

st.set_page_config(page_title="Validador Real-Time", page_icon="✈️")

st.title("🔍 Validador de Aeronave (Real-Time)")
st.markdown("Verifique agora qual aeronave está operando o seu voo.")

# Entrada de dados
numero_voo = st.text_input("Digite o número do voo (Ex: AA954):", "").upper().strip()

if st.button("Validar Aeronave"):
    if numero_voo:
        with st.spinner("Conectando aos radares..."):
            try:
                # Busca detalhes do voo específico
                detalhes = fr_api.get_flight_details(numero_voo)
                
                if detalhes and 'flight' in detalhes:
                    f = detalhes['flight']
                    aviao = f.get('aircraft', {})
                    modelo = aviao.get('model', {}).get('text', 'Não identificado')
                    matricula = aviao.get('registration', 'N/A')
                    
                    st.success(f"Voo {numero_voo} Localizado!")
                    
                    # Exibição dos dados técnicos
                    col1, col2 = st.columns(2)
                    col1.metric("Modelo", modelo)
                    col2.metric("Matrícula", matricula)
                    
                    # Explicação técnica para evitar divergências
                    st.info(f"**Nota Técnica:** Para o modelo {modelo}, os assentos disponíveis seguem a malha oficial da American Airlines (Ex: 6 Executiva / 9 Econômica).")
                else:
                    st.warning("Voo não encontrado no radar no momento. Certifique-se de que o voo está operando hoje.")
            except:
                st.error("Erro ao acessar dados em tempo real.")
    else:
        st.warning("Por favor, digite o número do voo.")
