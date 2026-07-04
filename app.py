import streamlit as st
import pandas as pd

st.set_page_config(page_title="Scouting Comuni Veneti", layout="wide")
st.title("Scouting Comuni Veneti (> 6000 abitanti)")

# Usiamo la cache per non riscaricare i dati a ogni interazione sulla pagina
@st.cache_data
def carica_e_filtra_dati():
    # 1. Scarichiamo l'IndicePA (Dati Istituzionali e PEC)
    url_indicepa = "https://indicepa.gov.it/ipa-dati/dataset/893df1ec-f232-4458-baae-55a0b77b73cc/resource/274f88e5-3d84-48f8-b385-eec3ef34731a/download/amministrazioni.txt"
    pa_df = pd.read_csv(url_indicepa, sep='\t', dtype=str)
    
    pa_veneto = pa_df[
        (pa_df['tipologia_istat'] == 'Comuni e loro Consorzi e Associazioni') &
        (pa_df['Regione'] == 'Veneto')
    ].copy()
    
    # 2. Scarichiamo i dati ISTAT sulla popolazione (da un repository Open Data stabile)
    url_pop = "https://raw.githubusercontent.com/opendatasicilia/comuni-italiani/main/dati/popolazione_2021.csv"
    url_comuni = "https://raw.githubusercontent.com/opendatasicilia/comuni-italiani/main/dati/comuni.csv"
    
    pop_df = pd.read_csv(url_pop, dtype=str)
    comuni_df = pd.read_csv(url_comuni, dtype=str)
    
    # Uniamo i due file ISTAT tramite il Codice ISTAT (pro_com_t)
    istat_df = pd.merge(comuni_df, pop_df, on='pro_com_t')
    
    # Trasformiamo la colonna popolazione in numeri veri e propri per poter applicare l'operatore matematico > 6000
    istat_df['pop_res_21'] = pd.to_numeric(istat_df['pop_res_21'], errors='coerce')
    
    # Filtriamo i comuni
    istat_grandi = istat_df[istat_df['pop_res_21'] > 6000].copy()
    
    # 3. INCROCIO DEI DATI (IndicePA + ISTAT)
    # Uniformiamo i nomi dei comuni in MAIUSCOLO per farli combaciare in modo infallibile
    pa_veneto['Comune_Upper'] = pa_veneto['Comune'].str.upper()
    istat_grandi['Comune_Upper'] = istat_grandi['comune'].str.upper()
    
    # Il parametro how='inner' terrà solo le righe in cui il nome del comune è presente in entrambe le tabelle
    dati_finali = pd.merge(pa_veneto, istat_grandi, on='Comune_Upper', how='inner')
    
    # 4. Pulizia estetica della tabella finale
    colonne_finali = ['Comune', 'Provincia', 'pop_res_21', 'Indirizzo', 'mail1', 'mail2', 'mail3']
    dati_finali = dati_finali[colonne_finali]
    
    # Rinominiamo le colonne per l'interfaccia utente
    dati_finali.rename(columns={
        'pop_res_21': 'Popolazione', 
        'mail1': 'PEC Primaria', 
        'mail2': 'PEC/Mail 2', 
        'mail3': 'Mail Protocollo'
    }, inplace=True)
    
    # Ordiniamo alfabeticamente per Provincia e, a parità di provincia, per Popolazione decrescente
    dati_finali.sort_values(by=['Provincia', 'Popolazione'], ascending=[True, False], inplace=True)
    dati_finali.reset_index(drop=True, inplace=True)
    
    return dati_finali

st.write("📥 Scaricamento e incrocio dati (IndicePA + Censimento ISTAT) in corso...")

dati = carica_e_filtra_dati()

st.success(f"✅ Trovati {len(dati)} comuni veneti con più di 6000 abitanti!")
st.dataframe(dati, use_container_width=True)

# Bottone di download per l'estrazione rapida
csv = dati.to_csv(index=False).encode('utf-8')
st.download_button(
    label="Scarica Tabella in CSV",
    data=csv,
    file_name='comuni_veneto_over_6000.csv',
    mime='text/csv',
)
