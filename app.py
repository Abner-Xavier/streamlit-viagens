import streamlit as st
import pandas as pd
from FlightRadar24 import FlightRadar24API

# Inicializa a API
fr_api = FlightRadar24API()

st.set_page_config(page_title="Validador de Aeronave", page_icon="✈️")

st.title("🔍 Validador de Aeronave (Real-Time)")
st.markdown("Verifique o modelo e matrícula da aeronave agora via radar.")

# Campo de entrada
flight_input = st.text_input("Digite o número do voo (Ex: AA954):", "").upper().strip()

if st.button("Validar agora"):
    if flight_input:
        with st.spinner(f"Localizando voo {flight_input}..."):
            try:
                # PASSO 1: Buscar voos ativos
                # A função correta não usa 'number', usamos filtros manuais para precisão
                all_flights = fr_api.get_flights()
                
                # Filtramos na lista o voo que corresponde ao número digitado
                target_flight = next((f for f in all_flights if f.number == flight_input or f.callsign == flight_input), None)
                
                if target_flight:
                    # PASSO 2: Obter detalhes técnicos do objeto encontrado
                    details = fr_api.get_flight_details(target_flight)
                    
                    f_data = details.get('flight', {})
                    aircraft = f_data.get('aircraft', {})
                    model = aircraft.get('model', {}).get('text', 'Não identificado')
                    registration = aircraft.get('registration', 'N/A')
                    
                    origin = f_data.get('airport', {}).get('origin', {}).get('code', {}).get('iata', '---')
                    destination = f_data.get('airport', {}).get('destination', {}).get('code', {}).get('iata', '---')

                    st.success(f"Voo {flight_input} Localizado!")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Modelo da Aeronave", model)
                        st.write(f"**Rota:** {origin} ➔ {destination}")
                    with col2:
                        st.metric("Matrícula", registration)
                        st.write(f"**Altitude:** {target_flight.altitude} pés")
                    
                    st.divider()
                    st.subheader("📊 Análise de Inventário")
                    if "777" in model:
                        st.info(f"Aeronave detectada: **{model}**. Configuração padrão para voos internacionais AA: **6 assentos na Executiva (J4 C2)**.")
                    else:
                        st.info(f"Modelo detectado: **{model}**. Verifique a disponibilidade para esta aeronave específica.")
                else:
                    st.warning(f"O voo {flight_input} não está ativo no radar neste momento.")
                    st.info("Nota: Voos aparecem aqui apenas quando estão com o transponder ligado (geralmente de 1h antes da decolagem até o pouso).")
            
            except Exception as e:
                st.error(f"Erro ao processar dados: {e}")
    else:
        st.warning("Por favor, insira um número de voo.")
