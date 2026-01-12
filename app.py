import streamlit as st
import pandas as pd

# 1. Configuração da Página
st.set_page_config(page_title="Busca Voos Pro", layout="wide")

# 2. Título e Estilo
st.title("✈️ Encontre seu próximo destino")
st.markdown("---")

# 3. Formulário de Busca
col1, col2, col3 = st.columns(3)

with col1:
    origem = st.text_input("Origem (IATA)", value="GRU")
with col2:
    destino = st.text_input("Destino (IATA)", value="JFK")
with col3:
    data = st.date_input("Data da viagem")

if st.button("Pesquisar Voos"):
    st.info(f"Buscando voos de {origem} para {destino}...")
    # Aqui entrará a lógica da API mais tarde
    
    # Simulação de resultado
    dados = {
        "Companhia": ["LATAM", "American Airlines", "Delta"],
        "Preço": ["R$ 3.200", "R$ 3.500", "R$ 3.800"],
        "Duração": ["10h", "9h 45min", "10h 10min"]
    }
    st.dataframe(pd.DataFrame(dados), use_container_width=True)
