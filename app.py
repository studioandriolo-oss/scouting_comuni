import streamlit as st
import pandas as pd
import requests
import io

st.set_page_config(page_title="Scouting Comuni Veneti", layout="wide")
st.title("Scouting Comuni Veneti (> 6000 abitanti)")

# --- FONTE DATI 1 & 2: INDICEPA + ISTAT ---
@st.cache_data
def carica_dati_base():
    # 1. Scaricamento IndicePA simulando un browser
    url_indicepa = "https://indicepa.gov.it/ipa-dati/dataset/893df1ec-f232-4458-baae-55a0b77b73cc/resource/274f88e5-3d84-48f8-b385-eec3ef34731a/download/amministrazioni.txt"
    
    # Questo dizionario 'headers' è il nostro travestimento da browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    # Facciamo la richiesta superando il firewall
    risposta_pa = requests.get(url_indicepa, headers=headers)
    risposta_pa.raise_for_status() # Verifica che non ci siano altri errori HTTP
    
    # Leggiamo il testo scaricato mettendolo in memoria (io.StringIO) e passandolo a Pandas
    pa_df = pd.read_csv(io.StringIO(risposta_pa.text), sep='\t', dtype=str)
    
    pa_veneto = pa_df[
        (pa_df['tipologia_istat'] == 'Comuni e loro Consorzi e Associazioni') &
        (pa_df['Regione'] == 'Veneto')
    ].copy()
    
    # Scaricamento dati ISTAT della popolazione
    url_pop = "https://raw.githubusercontent.com/opendatasicilia/comuni-italiani/main/dati/popolazione_2021.csv"
    url_comuni = "https://raw.githubusercontent.com/opendatasicilia/comuni-italiani/main/dati/comuni.csv"
    
    pop_df = pd.read_csv(url_pop, dtype=str)
    comuni_df = pd.read_csv(url_comuni, dtype=str)
    
    istat_df = pd.merge(comuni_df, pop_df, on='pro_com_t')
    istat_df['pop_res_21'] = pd.to_numeric(istat_df['pop_res_21'], errors='coerce')
    istat_grandi = istat_df[istat_df['pop_res_21'] > 6000].copy()
    
    # Uniformiamo in maiuscolo per l'incrocio
    pa_veneto['Comune_Upper'] = pa_veneto['Comune'].str.upper()
    istat_grandi['Comune_Upper'] = istat_grandi['comune'].str.upper()
    
    dati_uniti = pd.merge(pa_veneto, istat_grandi, on='Comune_Upper', how='inner')
    
    colonne_utili = ['Comune', 'Provincia', 'pop_res_21', 'Indirizzo', 'mail1', 'mail2', 'mail3']
    df_pulito = dati_uniti[colonne_utili].copy()
    df_pulito.rename(columns={
        'pop_res_21': 'Popolazione', 
        'mail1': 'PEC Primaria', 
        'mail2': 'PEC/Mail 2', 
        'mail3': 'Mail Protocollo'
    }, inplace=True)
    
    return df_pulito

# --- FONTE DATI 3: GEOGRAFIA DA OPENSTREETMAP ---
@st.cache_data
def cerca_comuni_su_arteria(codice_strada):
    """Interroga Overpass API per trovare i comuni veneti entro 2km da una strada"""
    overpass_url = "https://overpass-api.de/api/interpreter"
    
    # Query in Overpass QL: cerca la strada in Veneto e trova le relazioni dei comuni (admin_level=8) nel raggio di 2000 metri
    query = f"""
    [out:json][timeout:30];
    area["name"="Veneto"]->.regione;
    way["ref"="{codice_strada}"](area.regione)->.strada;
    rel(around.strada:2000)["admin_level"="8"];
    out tags;
    """
    
    try:
        risposta = requests.post(overpass_url, data={'data': query})
        dati_json = risposta.json()
        
        comuni_trovati = []
        for elemento in dati_json.get('elements', []):
            tags = elemento.get('tags', {})
            nome_comune = tags.get('name')
            if nome_comune:
                comuni_trovati.append(nome_comune.upper())
        return comuni_trovati
    except Exception as e:
        st.error(f"Errore durante l'interrogazione cartografica: {e}")
        return []

# --- INTERFACCIA UTENTE (STREAMLIT) ---

# Caricamento iniziale dei dati inseriti in cache
dati_base = carica_dati_base()

# Configurazione della barra laterale (Sidebar) per i filtri
st.sidebar.header("Filtri di Ricerca")

# Filtro 1: Selezione della Provincia
province_disponibili = ["Tutte"] + sorted(dati_base['Provincia'].unique().tolist())
provincia_scelta = st.sidebar.selectbox("Seleziona Provincia:", province_disponibili)

# Filtro 2: Inserimento dell'Arteria Stradale
strada_scelta = st.sidebar.text_input("Codice Arteria Stradale (es. SP247, SS11, SR11):", "").strip()

# Applicazione dei filtri al dataset base
risultati = dati_base.copy()

# Se l'utente sceglie una provincia specifica
if provincia_scelta != "Tutte":
    risultati = risultati[risultati['Provincia'] == provincia_scelta]

# Se l'utente inserisce una strada, attiviamo l'interrogazione a OpenStreetMap
if strada_scelta:
    with st.spinner(f"🔍 Analisi geografica dell'arteria {strada_scelta} in corso..."):
        elenco_comuni_strada = cerca_comuni_su_arteria(strada_scelta)
        
    if elenco_comuni_strada:
        # Teniamo solo i comuni del nostro database che compaiono nell'elenco geografico di OSM
        risultati['Comune_Upper'] = risultati['Comune'].str.upper()
        risultati = risultati[risultati['Comune_Upper'].isin(elenco_comuni_strada)]
        risultati.drop(columns=['Comune_Upper'], errors='ignore', inplace=True)
        st.sidebar.success(f"Strada individuata! Filtrati i comuni adiacenti.")
    else:
        st.sidebar.warning("Nessun comune trovato per questa sigla stradale in Veneto. Verifica il codice (es. SP247).")

# --- VISUALIZZAZIONE RISULTATI ---

st.subheader("Risultati dello Scouting")
st.write(f"Record trovati: **{len(risultati)}** comuni corrispondenti ai criteri impostati.")

# Ordiniamo per pulizia visiva
risultati.sort_values(by=['Provincia', 'Comune'], inplace=True)
risultati.reset_index(drop=True, inplace=True)

# Mostriamo la tabella interattiva
st.dataframe(risultati, use_container_width=True)

# Bottone per esportare i dati estratti
if not risultati.empty:
    csv = risultati.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Scarica Report in CSV",
        data=csv,
        file_name='scouting_comuni_filtrati.csv',
        mime='text/csv',
    )
