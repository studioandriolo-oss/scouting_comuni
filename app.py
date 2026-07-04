import streamlit as st
import pandas as pd

st.set_page_config(page_title="Scouting Comuni Veneti", layout="wide")
st.title("Scouting Comuni Veneti")

# Usiamo la cache di Streamlit per evitare di riscaricare i dati della PA a ogni clic
@st.cache_data
def carica_dati_indicepa():
    # URL ufficiale del dataset IndicePA
    url_indicepa = "https://indicepa.gov.it/ipa-dati/dataset/893df1ec-f232-4458-baae-55a0b77b73cc/resource/274f88e5-3d84-48f8-b385-eec3ef34731a/download/amministrazioni.txt"
    
    # Pandas legge il file da internet (è separato da Tabulazioni, quindi sep='\t')
    tabella_pa = pd.read_csv(url_indicepa, sep='\t', dtype=str)
    
    # Filtriamo solo i comuni e solo in Veneto
    comuni_veneto = tabella_pa[
        (tabella_pa['tipologia_istat'] == 'Comuni e loro Consorzi e Associazioni') &
        (tabella_pa['Regione'] == 'Veneto')
    ]
    
    # Selezioniamo le colonne utili (codice istat, nome, provincia, indirizzo, pec/mail)
    colonne_utili = ['cod_amm', 'Comune', 'Provincia', 'Indirizzo', 'mail1', 'mail2', 'mail3']
    return comuni_veneto[colonne_utili]

st.write("Scaricamento dei dati istituzionali in corso dal database governativo...")

# Richiamiamo la funzione
dati = carica_dati_indicepa()

# Mostriamo il risultato
st.success(f"Trovati {len(dati)} comuni in Veneto.")
st.dataframe(dati, use_container_width=True)
