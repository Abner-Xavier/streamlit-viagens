import streamlit as st
import pandas as pd
from FlightRadar24 import FlightRadar24API

# Inicializa a API
fr_api = FlightRadar24API()

st.set_page_config(page_title="Validador de Aeronave", page_icon="✈️")

st.title("🔍 Validador de Aeronave (Real-Time)")
st.markdown("Verifique o modelo e matrícula da aeronave agora via radar.")

flight_number = st.text_input("Digite o número do voo (Ex: AA954):", "").upper().strip()

if st.button("Validar agora"):
    if flight_number:
        with st.spinner(f"Localizando voo {flight_number} no espaço aéreo..."):
            try:
                # PASSO 1: Buscar o voo na malha ativa
                flights = fr_api.get_flights(number=flight_number)
                
                if flights:
                    # Pegamos o primeiro voo encontrado (o mais recente/ativo)
                    target_flight = flights[0]
                    
                    # PASSO 2: Obter detalhes usando o OBJETO do voo, não o texto
                    details = fr_api.get_flight_details(target_flight)
                    
                    # Extração de dados com segurança (usando .get para evitar erros)
                    f_data = details.get('flight', {})
                    aircraft = f_data.get('aircraft', {})
                    model = aircraft.get('model', {}).get('text', 'Não identificado')
                    registration = aircraft.get('registration', 'N/A')
                    
                    origin = f_data.get('airport', {}).get('origin', {}).get('code', {}).get('iata', '---')
                    destination = f_data.get('airport', {}).get('destination', {}).get('code', {}).get('iata', '---')

                    st.success(f"Voo {flight_number} Localizado!")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Modelo da Aeronave", model)
                        st.write(f"**Rota:** {origin} ➔ {destination}")
                    with col2:
                        st.metric("Matrícula", registration)
                        st.write(f"**Altitude:** {target_flight.altitude} pés")
                    
                    # Lógica de assentos baseada no modelo real detectado
                    st.divider()
                    st.subheader("📊 Análise de Inventário Estimada")
                    if "777" in model:
                        st.info(f"Aeronave de grande porte ({model}). Configuração padrão AA: **6 assentos Executiva (J4 C2)**.")
                    else:
                        st.info(f"Aeronave identificada: {model}. Verifique o mapa de assentos para configurações específicas.")
                
                else:
                    st.warning(f"O voo {flight_number} não foi encontrado no radar agora. Ele pode não ter decolado ou o transponder está desligado.")
                    st.caption("Dica: Tente pesquisar um voo que você sabe que está no ar agora (ex: um voo da LATAM ou GOL saindo de GRU).")
            
            except Exception as e:
                st.error(f"Erro técnico ao processar dados: {e}")
    else:
        st.warning("Por favor, insira um número de voo.")

st.sidebar.markdown("---")
st.sidebar.caption("Dados em tempo real via FlightRadar24 API")
