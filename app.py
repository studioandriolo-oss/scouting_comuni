import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Scouting Comuni Veneti", layout="wide")
st.title("Scouting Comuni Veneti (> 6000 abitanti)")

# --- FONTE DATI 1 & 2: INDICEPA + ISTAT ---
@st.cache_data
def carica_dati_base():
    # 1. Lettura File (Usiamo latin1 che è il formato spesso usato dalla PA italiana)
    try:
        pa_df = pd.read_csv("amministrazioni.txt", sep='\t', dtype=str, encoding='latin1', on_bad_lines='skip')
    except FileNotFoundError:
        st.error("❌ File 'amministrazioni.txt' non trovato nel repository GitHub!")
        return pd.DataFrame(), pd.DataFrame()

    # Salviamo una copia grezza intatta per il debug visivo
    pa_raw = pa_df.copy()

    # Puliamo i nomi delle colonne (a volte la PA inserisce spazi prima del nome della colonna)
    pa_df.columns = pa_df.columns.str.strip()

    # FILTRO ANTIPROIETTILE: Usiamo le sigle esatte delle province venete, saltando i campi descrittivi
    province_veneto = ['VI', 'VR', 'PD', 'TV', 'VE', 'RO', 'BL']
    
    if 'Provincia' in pa_df.columns:
        pa_df['Provincia'] = pa_df['Provincia'].astype(str).str.strip().str.upper()
        pa_veneto = pa_df[pa_df['Provincia'].isin(province_veneto)].copy()
    else:
        st.error("❌ La colonna 'Provincia' è assente dal file IndicePA. Hanno cambiato tracciato!")
        return pd.DataFrame(), pa_raw

    # 2. Dati ISTAT
    url_pop = "https://raw.githubusercontent.com/opendatasicilia/comuni-italiani/main/dati/popolazione_2021.csv"
    url_comuni = "https://raw.githubusercontent.com/opendatasicilia/comuni-italiani/main/dati/comuni.csv"
    
    pop_df = pd.read_csv(url_pop, dtype=str)
    comuni_df = pd.read_csv(url_comuni, dtype=str)
    
    istat_df = pd.merge(comuni_df, pop_df, on='pro_com_t')
    istat_df['pop_res_21'] = pd.to_numeric(istat_df['pop_res_21'], errors='coerce')
    istat_grandi = istat_df[istat_df['pop_res_21'] > 6000].copy()
    
    # 3. Incrocio
    if 'Comune' in pa_veneto.columns:
        pa_veneto['Comune_Upper'] = pa_veneto['Comune'].astype(str).str.strip().str.upper()
    else:
        st.error("❌ La colonna 'Comune' manca in IndicePA.")
        return pd.DataFrame(), pa_raw
        
    istat_grandi['Comune_Upper'] = istat_grandi['comune'].astype(str).str.strip().str.upper()
    
    dati_uniti = pd.merge(pa_veneto, istat_grandi, on='Comune_Upper', how='inner')
    
    # Selezioniamo solo le colonne che esistono per evitare crash
    colonne_utili = ['Comune', 'Provincia', 'pop_res_21', 'Indirizzo', 'mail1', 'mail2', 'mail3']
    colonne_presenti = [c for c in colonne_utili if c in dati_uniti.columns]
    
    df_pulito = dati_uniti[colonne_presenti].copy()
    
    rinomine = {
        'pop_res_21': 'Popolazione', 
        'mail1': 'PEC Primaria', 
        'mail2': 'PEC/Mail 2', 
        'mail3': 'Mail Protocollo'
    }
    df_pulito.rename(columns={k: v for k, v in rinomine.items() if k in df_pulito.columns}, inplace=True)
    
    return df_pulito, pa_raw

# --- FONTE DATI 3: GEOGRAFIA DA OPENSTREETMAP ---
@st.cache_data
def cerca_comuni_su_arteria(codice_strada):
    overpass_url = "https://overpass-api.de/api/interpreter"
    codice_strada = codice_strada.upper().strip()
    
    # Crea la variante con spazio (es. se l'utente digita "SP247", cerca anche "SP 247")
    variante_spazio = f"{codice_strada[:2]} {codice_strada[2:]}" if len(codice_strada) > 2 and codice_strada[:2].isalpha() and codice_strada[2:].isdigit() else codice_strada

    query = f"""
    [out:json][timeout:60];
    area["name"="Veneto"]->.regione;
    (
      way["ref"="{codice_strada}"](area.regione);
      way["ref"="{variante_spazio}"](area.regione);
    )->.strada;
    rel(around.strada:2000)["admin_level"="8"];
    out tags;
    """
    
    try:
        risposta = requests.post(overpass_url, data={'data': query})
        if risposta.status_code != 200:
            st.error(f"Errore dal server della mappa: {risposta.status_code}. Riprova tra poco.")
            return []
            
        dati_json = risposta.json()
        comuni_trovati = []
        for elemento in dati_json.get('elements', []):
            nome = elemento.get('tags', {}).get('name')
            if nome:
                comuni_trovati.append(nome.strip().upper())
        return comuni_trovati
    except Exception as e:
        st.error(f"Errore di connessione cartografica: {e}")
        return []

# --- INTERFACCIA UTENTE (STREAMLIT) ---

st.write("🔄 Caricamento e incrocio dati in corso...")
dati_base, pa_raw = carica_dati_base()

# STRUMENTO DI DEBUG NELLA BARRA LATERALE
st.sidebar.markdown("---")
if st.sidebar.checkbox("🛠️ Modalità Debug (Mostra file grezzo)"):
    st.warning("Visualizzazione delle prime 50 righe del file amministrazioni.txt così come scaricato dal Ministero:")
    st.dataframe(pa_raw.head(50))
    st.stop() # Blocca l'esecuzione del resto dell'app per permetterti di ispezionare la tabella

if dati_base.empty:
    st.warning("⚠️ La tabella di base è vuota. Attiva la 'Modalità Debug' nella barra laterale sinistra per verificare l'aspetto dei dati scaricati.")
else:
    st.sidebar.header("Filtri di Ricerca")
    
    province_disponibili = ["Tutte"] + sorted(dati_base['Provincia'].dropna().unique().tolist())
    provincia_scelta = st.sidebar.selectbox("Seleziona Provincia:", province_disponibili)
    
    strada_scelta = st.sidebar.text_input("Codice Arteria (es. SP247 o SS11):", "").strip()
    
    risultati = dati_base.copy()
    
    if provincia_scelta != "Tutte":
        risultati = risultati[risultati['Provincia'] == provincia_scelta]
    
    if strada_scelta:
        with st.spinner(f"🔍 Scansione della mappa per l'arteria {strada_scelta} (può richiedere fino a 30 secondi)..."):
            elenco_comuni_strada = cerca_comuni_su_arteria(strada_scelta)
            
        if elenco_comuni_strada:
            risultati['Comune_Upper'] = risultati['Comune'].astype(str).str.strip().str.upper()
            risultati = risultati[risultati['Comune_Upper'].isin(elenco_comuni_strada)]
            risultati.drop(columns=['Comune_Upper'], errors='ignore', inplace=True)
            st.sidebar.success("✅ Strada individuata! Comuni filtrati.")
        else:
            st.sidebar.warning(f"⚠️ Nessun comune trovato. Su OpenStreetMap la {strada_scelta} potrebbe essere mappata diversamente.")
    
    # --- VISUALIZZAZIONE RISULTATI ---
    st.subheader("Risultati dello Scouting")
    st.write(f"Record trovati: **{len(risultati)}** comuni corrispondenti ai criteri impostati.")
    
    if not risultati.empty:
        risultati.sort_values(by=['Provincia', 'Comune'], inplace=True)
        risultati.reset_index(drop=True, inplace=True)
        st.dataframe(risultati, use_container_width=True)
        
        csv = risultati.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Scarica Report in CSV",
            data=csv,
            file_name='scouting_comuni_filtrati.csv',
            mime='text/csv',
        )
