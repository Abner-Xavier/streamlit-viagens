import streamlit as st

st.set_page_config(page_title="Bot de Viagens", layout="centered")

st.title("✈️ Bot de Pesquisa de Viagens")

st.write("Ferramenta interna para pesquisa de hotéis e voos")

cidade = st.text_input("Cidade")
classe = st.selectbox(
    "Classe",
    ["Econômica", "Business", "First"]
)

if st.button("Pesquisar"):
    st.success("Busca realizada com sucesso 🚀")
    st.write("Cidade:", cidade)
    st.write("Classe:", classe)
