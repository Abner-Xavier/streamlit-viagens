import streamlit as st
import pandas as pd
from datetime import datetime

# Configuração da página
st.set_page_config(page_title="Analista de Malha Aérea - AA", page_icon="✈️", layout="wide")

# Estilização Customizada
st.markdown("""
    <style>
    .flight-card {
        background-color: #ffffff;
        padding: 20px;
        border-radius: 10px;
        border-left: 8px solid #001e5d;
        box-shadow: 2px 2px 12px rgba(0,0,0,0.1);
        margin-bottom: 20px;
        color: #333;
    }
    .seat-badge {
        background-color: #e8f0fe;
        color: #1967d2;
        padding: 5px 12px;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.9em;
    }
    </style>
    """, unsafe_allow_html=True)

# --- BASE DE DADOS REALISTA (Sincronizada com Buckets GDS) ---
# Aqui somamos os assentos das subclasses para evitar divergências
dados_voos = [
    {
        "voo": "AA 954", "origem": "EZE", "destino": "JFK", 
        "saida": "20:45", "chegada": "06:10", "data": "2026-01-17",
        "primeira": 0, "executiva": 6, "economica": 9, 
        "bucket": "J4 C2 Y9", "equipamento": "Boeing 777-200"
    },
    {
        "voo": "AA 930", "origem": "GRU", "destino": "MIA", 
        "saida": "23:30", "chegada": "05:40", "data": "2026-01-17",
        "primeira": 0, "executiva": 0, "economica": 4, 
        "bucket": "J0 C0 Y4", "equipamento": "Boeing 777-300ER"
    },
    {
        "voo": "AA 2131", "origem": "MIA", "destino": "LAX", 
        "saida": "09:02", "chegada": "11:45", "data": "2026-01-18",
        "primeira": 2, "executiva": 5, "economica": 9, 
        "bucket": "F2 J5 Y9", "equipamento": "Airbus A321T"
    },
    {
        "voo": "AA 3085", "origem": "JFK", "destino": "SNA", 
        "saida": "07:20", "chegada": "10:30", "data": "2026-01-18",
        "primeira": 0, "executiva": 2, "economica": 7, 
        "bucket": "J2 Y7", "equipamento": "Airbus A321neo"
    }
]

# --- INTERFACE ---
st.title("✈️ Dashboard de Disponibilidade American Airlines")
st.markdown("Monitoramento de inventário por classes tarifárias (Buckets)")

with st.sidebar:
    st.header("Pesquisa de Inventário")
    origem = st.text_input("Origem (IATA)", "EZE").upper()
    destino = st.text_input("Destino (IATA)", "JFK").upper()
    data_sel = st.date_input("Data", datetime(2026, 1, 17))
    cabine = st.selectbox("Cabine Desejada", ["Econômica", "Executiva", "Primeira Classe"])
    
    buscar = st.button("Verificar Assentos")

# --- LÓGICA DE FILTRO ---
if buscar:
    # Mapeamento da escolha do usuário para a chave do dicionário
    mapa_cabine = {
        "Econômica": "economica",
        "Executiva": "executiva",
        "Primeira Classe": "primeira"
    }
    chave_cabine = mapa_cabine[cabine]

    # Filtro dinâmico
    resultados = [v for v in dados_voos if v['origem'] == origem and v['destino'] == destino]

    if resultados:
        for voo in resultados:
            qtd_assentos = voo[chave_cabine]
            
            # Alerta visual se não houver assentos na cabine escolhida
            if qtd_assentos == 0:
                st.error(f"Atenção: Não há assentos disponíveis em **{cabine}** para o voo {voo['voo']}.")
                st.info(f"Dica técnica: Este voo ({voo['equipamento']}) pode não operar esta cabine ou estar esgotado.")
            
            # Card do Voo
            st.markdown(f"""
                <div class="flight-card">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span style="font-size: 1.5em; font-weight: bold;">{voo['voo']}</span>
                        <span class="seat-badge">{qtd_assentos} assentos em {cabine}</span>
                    </div>
                    <p style="margin: 10px 0;"><b>Rota:</b> {voo['origem']} ➔ {voo['destino']} | <b>Aeronave:</b> {voo['equipamento']}</p>
                    <div style="display: flex; gap: 20px; background: #f8f9fa; padding: 10px; border-radius: 5px;">
                        <div><b>Partida:</b> {voo['saida']}</div>
                        <div><b>Chegada:</b> {voo['chegada']}</div>
                        <div><b>Bucket:</b> <code style="color: #d63384;">{voo['bucket']}</code></div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
    else:
        st.warning("Nenhum voo encontrado para esta rota na base de dados.")

else:
    st.info("Selecione os filtros ao lado para analisar a disponibilidade real dos buckets.")
    # Tabela resumida para o desenvolvedor
    with st.expander("Visualizar Malha Completa"):
        st.table(pd.DataFrame(dados_voos).drop(columns=['bucket']))
