import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Scouting Comuni Veneti", layout="wide")
st.title("Scouting Comuni Veneti (> 6000 abitanti)")

@st.cache_data
def carica_dati_base():
    # --- 1. LETTURA INDICEPA ---
    try:
        # L'encoding 'utf-8-sig' neutralizza il bug dei caratteri sporchi (ï»¿) a inizio file
        pa_df = pd.read_csv("amministrazioni.txt", sep='\t', dtype=str, encoding='utf-8-sig', on_bad_lines='skip')
    except FileNotFoundError:
        st.error("❌ File 'amministrazioni.txt' non trovato nel repository GitHub!")
        return pd.DataFrame(), pd.DataFrame()

    pa_raw = pa_df.copy()
    pa_df.columns = pa_df.columns.str.strip()

    # Filtriamo in modo specifico solo gli Enti che sono "Comuni" veri e propri in "Veneto"
    if 'tipologia_istat' in pa_df.columns and 'Regione' in pa_df.columns:
        pa_veneto = pa_df[
            (pa_df['tipologia_istat'].astype(str).str.contains('Comuni', case=False, na=False)) &
            (pa_df['Regione'].astype(str).str.strip().str.upper() == 'VENETO')
        ].copy()
    else:
        st.error("❌ Colonne 'tipologia_istat' o 'Regione' mancanti. Il tracciato del Ministero è cambiato.")
        return pd.DataFrame(), pa_raw

    # --- 2. LETTURA ISTAT ---
    url_pop = "https://raw.githubusercontent.com/opendatasicilia/comuni-italiani/main/dati/popolazione_2021.csv"
    url_comuni = "https://raw.githubusercontent.com/opendatasicilia/comuni-italiani/main/dati/comuni.csv"
    
    pop_df = pd.read_csv(url_pop, dtype=str)
    comuni_df = pd.read_csv(url_comuni, dtype=str)
    
    # Trucco da ingegneri dei dati: forziamo i codici ISTAT a numeri interi.
    # Così evitiamo che i file perdano gli zeri iniziali ("001001" vs "1001") facendo fallire l'incrocio.
    comuni_df['codice_int'] = pd.to_numeric(comuni_df['pro_com_t'], errors='coerce')
    pop_df['codice_int'] = pd.to_numeric(pop_df['pro_com_t'], errors='coerce')
    
    istat_df = pd.merge(comuni_df, pop_df, on='codice_int', how='inner')
    istat_df['pop_res_21'] = pd.to_numeric(istat_df['pop_res_21'], errors='coerce')
    istat_grandi = istat_df[istat_df['pop_res_21'] > 6000].copy()
    
    # --- 3. INCROCIO DEI DUE DATABASE ---
    pa_veneto['Comune_Upper'] = pa_veneto['Comune'].astype(str).str.strip().str.upper()
    istat_grandi['Comune_Upper'] = istat_grandi['comune'].astype(str).str.strip().str.upper()
    
    dati_uniti = pd.merge(pa_veneto, istat_grandi, on='Comune_Upper', how='inner')
    
    # Prepariamo la tabella pulita verificando le colonne disponibili
    colonne_utili = ['Comune', 'Provincia', 'pop_res_21', 'Indirizzo', 'mail1', 'mail2', 'mail3', 'sito_istituzionale']
    colonne_presenti = [c for c in colonne_utili if c in dati_uniti.columns]
    
    df_pulito = dati_uniti[colonne_presenti].copy()
    
    rinomine = {
        'pop_res_21': 'Popolazione', 
        'mail1': 'PEC/Mail 1', 
        'mail2': 'PEC/Mail 2', 
        'mail3': 'PEC/Mail Protocollo',
        'sito_istituzionale': 'Sito Web'
    }
    df_pulito.rename(columns={k: v for k, v in rinomine.items() if k in df_pulito.columns}, inplace=True)
    
    return df_pulito, pa_raw

# --- FONTE DATI 3: GEOGRAFIA DA OPENSTREETMAP ---
@st.cache_data
def cerca_comuni_su_arteria(codice_strada):
    overpass_url = "https://overpass-api.de/api/interpreter"
    codice_strada = codice_strada.upper().strip()
    
    # Crea in automatico la variante con lo spazio (es. "SP247" diventa anche "SP 247")
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
            st.error("Errore di connessione ai server cartografici.")
            return []
            
        dati_json = risposta.json()
        return [elemento.get('tags', {}).get('name').strip().upper() for elemento in dati_json.get('elements', []) if elemento.get('tags', {}).get('name')]
    except Exception:
        return []

# --- INTERFACCIA UTENTE ---

st.write("🔄 Calcolo incroci database in corso...")
dati_base, pa_raw = carica_dati_base()

st.sidebar.markdown("---")
if st.sidebar.checkbox("🛠️ Modalità Debug (Mostra file grezzo)"):
    st.warning("Visualizzazione file puro dal Ministero:")
    st.dataframe(pa_raw.head(50))
    st.stop()

if dati_base.empty:
    st.error("⚠️ Nessun dato trovato. La tabella è ancora vuota.")
else:
    st.sidebar.header("Filtri di Ricerca")
    
    province_disponibili = ["Tutte"] + sorted(dati_base['Provincia'].dropna().unique().tolist())
    provincia_scelta = st.sidebar.selectbox("Seleziona Provincia:", province_disponibili)
    
    strada_scelta = st.sidebar.text_input("Codice Arteria (es. SP247 o SS11):", "").strip()
    
    risultati = dati_base.copy()
    
    if provincia_scelta != "Tutte":
        risultati = risultati[risultati['Provincia'] == provincia_scelta]
    
    if strada_scelta:
        with st.spinner(f"🔍 Mappatura geografica dell'arteria {strada_scelta}..."):
            elenco_comuni_strada = cerca_comuni_su_arteria(strada_scelta)
            
        if elenco_comuni_strada:
            risultati['Comune_Upper'] = risultati['Comune'].astype(str).str.strip().str.upper()
            risultati = risultati[risultati['Comune_Upper'].isin(elenco_comuni_strada)]
            risultati.drop(columns=['Comune_Upper'], errors='ignore', inplace=True)
            st.sidebar.success("✅ Strada individuata! Comuni limitrofi filtrati.")
        else:
            st.sidebar.warning(f"⚠️ Nessun comune trovato. Verifica il formato della strada sulla mappa.")
    
    st.subheader("Risultati dello Scouting")
    st.write(f"Record validi trovati: **{len(risultati)}**")
    
    if not risultati.empty:
        risultati.sort_values(by=['Provincia', 'Comune'], inplace=True)
        risultati.reset_index(drop=True, inplace=True)
        st.dataframe(risultati, use_container_width=True)
        
        csv = risultati.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Scarica Report CSV", data=csv, file_name='scouting_veneto.csv', mime='text/csv')
