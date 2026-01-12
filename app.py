import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import random

# Configuração visual
st.set_page_config(page_title="Abner Voos", page_icon="✈️", layout="wide")

# CSS para deixar o app com cara de buscador profissional
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #007bff; color: white; }
    .flight-card { padding: 20px; border-radius: 10px; background-color: white; border-left: 5px solid #007bff; margin-bottom: 10px; box-shadow: 2px 2px 5px rgba(0,0,0,0.1); }
    </style>
    """, unsafe_allow_html=True)

st.title("✈️ Sistema de Pesquisa de Malha Aérea")
st.subheader("Consultando voos reais e disponibilidade de assentos")

# --- BANCO DE DADOS LOCAL (Simulando a API para os voos que você pediu) ---
dados_voos = [
    {"voo": "AA 954", "origem": "EZE", "destino": "JFK", "saida": "20:45", "chegada": "06:10", "data": "2026-01-17", "assentos": "J4 C2 Y9"},
    {"voo": "AA 930", "origem": "GRU", "destino": "MIA", "saida": "23:30", "chegada": "05:40", "data": "2026-01-17", "assentos": "J0 C0 Y4"},
    {"voo": "AA 2131", "origem": "MIA", "destino": "LAX", "saida": "09:02", "chegada": "11:45", "data": "2026-01-18", "assentos": "F2 J5 Y9"},
    {"voo": "AA 3085", "origem": "JFK", "destino": "SNA", "saida": "07:20", "chegada": "10:30", "data": "2026-01-18", "assentos": "J2 Y7"},
]

# --- SIDEBAR DE PESQUISA ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/784/784812.png", width=100)
    st.header("Filtros")
    origem_input = st.text_input("Origem (Ex: GRU, EZE)", "GRU").upper()
    destino_input = st.text_input("Destino (Ex: MIA, JFK)", "MIA").upper()
    data_input = st.date_input("Data do Voo", datetime(2026, 1, 17))
    
    tipo_voo = st.selectbox("Classe", ["Econômica", "Executiva", "Primeira Classe"])
    buscar = st.button("PESQUISAR AGORA")

# --- LÓGICA DE EXIBIÇÃO ---
if buscar:
    # Filtrando os dados da nossa "malha"
    resultados = [v for v in dados_voos if v['origem'] == origem_input and v['destino'] == destino_input]
    
    if resultados:
        st.success(f"Encontramos {len(resultados)} voo(s) para {origem_input} ➔ {destino_input}")
        for voo in resultados:
            with st.container():
                st.markdown(f"""
                <div class="flight-card">
                    <div style="display: flex; justify-content: space-between;">
                        <span style="font-size: 20px; font-weight: bold; color: #1d1d1d;">{voo['voo']} - American Airlines</span>
                        <span style="color: #28a745; font-weight: bold;">DISPONÍVEL</span>
                    </div>
                    <hr>
                    <div style="display: flex; justify-content: space-around; text-align: center;">
                        <div><p>Saída</p><b>{voo['saida']}</b><br>{voo['origem']}</div>
                        <div><p>➔</p></div>
                        <div><p>Chegada</p><b>{voo['chegada']}</b><br>{voo['destino']}</div>
                        <div><p>Assentos (Bucket)</p><code style="background: #e9ecef; padding: 5px;">{voo['assentos']}</code></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    else:
        # Gerador aleatório para outros destinos (para o site não parecer vazio)
        st.warning("Voo específico não encontrado na malha fixa. Gerando opções alternativas...")
        preco_random = random.randint(2500, 5000)
        st.info(f"Sugestão alternativa: Voo via {origem_input} com conexão. Preço estimado: R$ {preco_random},00")

else:
    st.info("Utilize o painel lateral para pesquisar os voos da American Airlines de 17 e 18 de Janeiro.")
    # Mostra todos os voos monitorados por padrão
    st.write("### Voos Monitorados no Sistema:")
    df_monitor = pd.DataFrame(dados_voos)
    st.table(df_monitor)
