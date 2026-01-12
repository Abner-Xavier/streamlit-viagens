import streamlit as st
from FlightRadar24 import FlightRadar24API
import pandas as pd

# Inicialização da API
fr_api = FlightRadar24API()

st.set_page_config(page_title="Validador de Aeronave Real-Time", page_icon="✈️")

st.title("🔍 Validador de Aeronave por Número de Voo")
st.markdown("Consulte os dados exatos da aeronave operando agora via FlightRadar24.")

# Campo de entrada focado apenas no número do voo
flight_number = st.text_input("Digite o número do voo (ex: AA954, AA930):", "").upper().strip()

if st.button("Validar Aeronave"):
    if flight_number:
        with st.spinner(f"Buscando dados técnicos para {flight_number}..."):
            try:
                # Busca detalhes específicos do voo
                details = fr_api.get_flight_details(flight_number)
                
                if details and 'flight' in details:
                    f = details['flight']
                    
                    # Extração de dados técnicos da aeronave
                    aircraft_info = f.get('aircraft', {})
                    model = aircraft_info.get('model', {}).get('text', 'Não identificado')
                    registration = aircraft_info.get('registration', 'N/A')
                    country = aircraft_info.get('country', {}).get('name', 'N/A')
                    
                    # Dados de rota para contexto
                    origin = f.get('airport', {}).get('origin', {}).get('code', {}).get('iata', '---')
                    dest = f.get('airport', {}).get('destination', {}).get('code', {}).get('iata', '---')
                    status = f.get('status', {}).get('text', 'Status desconhecido')

                    # Exibição dos resultados
                    st.success(f"Voo {flight_number} Localizado!")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("✈️ Dados da Aeronave")
                        st.write(f"**Modelo:** {model}")
                        st.write(f"**Matrícula (Tail Number):** {registration}")
                        st.write(f"**País de Registro:** {country}")
                    
                    with col2:
                        st.subheader("📍 Operação")
                        st.write(f"**Rota:** {origin} ➔ {dest}")
                        st.write(f"**Status:** {status}")

                    # Explicação técnica sobre capacidade
                    st.info(f"""
                    **Análise Técnica:** O modelo **{model}** determina a configuração de cabines. 
                    Se for um Boeing 777-200 ou 777-300ER da AA, a configuração premium é focada em Business Class. 
                    A disponibilidade de assentos (Buckets) é derivada deste modelo de aeronave.
                    """)
                else:
                    st.error("Voo não encontrado ou não está ativo no radar no momento.")
                    st.caption("Nota: Voos só aparecem quando há um plano de voo ativo para as próximas horas.")
            
            except Exception as e:
                st.error(f"Erro ao conectar com o serviço de radar: {e}")
    else:
        st.warning("Por favor, insira um número de voo.")

# Rodapé profissional para o GitHub
st.markdown("---")
st.caption("Repositório: Abner-Xavier/streamlit-viagens | Dados providos por FlightRadar24API")
