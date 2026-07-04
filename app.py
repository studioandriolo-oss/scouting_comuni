import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Scouting Comuni Veneti", layout="wide")
st.title("Scouting Comuni Veneti (> 6000 abitanti)")

@st.cache_data
def carica_dati_completi():
    # --- 1. LETTURA AMMINISTRAZIONI (Protocollo Generale) ---
    try:
        pa_df = pd.read_csv("amministrazioni.txt", sep='\t', dtype=str, encoding='utf-8-sig', on_bad_lines='skip')
    except FileNotFoundError:
        st.error("❌ File 'amministrazioni.txt' non trovato su GitHub.")
        return pd.DataFrame()
        
    pa_df.columns = pa_df.columns.str.strip()
    
    if 'tipologia_istat' in pa_df.columns and 'Regione' in pa_df.columns:
        pa_veneto = pa_df[
            (pa_df['tipologia_istat'].astype(str).str.contains('Comuni', case=False, na=False)) &
            (pa_df['Regione'].astype(str).str.strip().str.upper() == 'VENETO')
        ].copy()
    else:
        return pd.DataFrame()

 # --- 2. LETTURA UNITA' ORGANIZZATIVE (Uffici Tecnici e Dirigenti) ---
    try:
        ou_df = pd.read_csv("ou.txt", sep='\t', dtype=str, encoding='utf-8-sig', on_bad_lines='skip')
        
        # Filtriamo solo gli uffici che ci interessano tramite parole chiave
        keywords = 'TECNIC|LAVORI|PUBBLIC|EDILIZIA|PATRIMONIO|MANUTENZION|PNRR'
        if 'des_ou' in ou_df.columns:
            uffici_tecnici = ou_df[ou_df['des_ou'].astype(str).str.contains(keywords, case=False, na=False)].copy()
        else:
            uffici_tecnici = pd.DataFrame()
    except FileNotFoundError:
        st.warning("⚠️ File 'ou.txt' mancante. Caricalo su GitHub per vedere i nomi dei dirigenti e le mail degli uffici tecnici!")
        uffici_tecnici = pd.DataFrame()

    # --- 3. LETTURA ISTAT (Popolazione) ---
    url_pop = "https://raw.githubusercontent.com/opendatasicilia/comuni-italiani/main/dati/popolazione_2021.csv"
    url_comuni = "https://raw.githubusercontent.com/opendatasicilia/comuni-italiani/main/dati/comuni.csv"
    
    pop_df = pd.read_csv(url_pop, dtype=str)
    comuni_df = pd.read_csv(url_comuni, dtype=str)
    
    comuni_df['codice_int'] = pd.to_numeric(comuni_df['pro_com_t'], errors='coerce')
    pop_df['codice_int'] = pd.to_numeric(pop_df['pro_com_t'], errors='coerce')
    
    istat_df = pd.merge(comuni_df, pop_df, on='codice_int', how='inner')
    istat_df['pop_res_21'] = pd.to_numeric(istat_df['pop_res_21'], errors='coerce')
    istat_grandi = istat_df[istat_df['pop_res_21'] > 6000].copy()
    
    # --- 4. INCROCI MULTIPLI ---
    # A. Incrocio Comuni + Popolazione
    pa_veneto['Comune_Upper'] = pa_veneto['Comune'].astype(str).str.strip().str.upper()
    istat_grandi['Comune_Upper'] = istat_grandi['comune'].astype(str).str.strip().str.upper()
    comuni_base = pd.merge(pa_veneto, istat_grandi, on='Comune_Upper', how='inner')
    
    # B. Incrocio con gli Uffici Tecnici (Se ou.txt è presente)
    if not uffici_tecnici.empty and 'cod_amm' in comuni_base.columns and 'cod_amm' in uffici_tecnici.columns:
        # Uniamo i dati. how='left' significa che se un comune non ha inserito l'ufficio tecnico nel database, mostriamo comunque il comune
        dati_finali = pd.merge(comuni_base, uffici_tecnici, on='cod_amm', how='left', suffixes=('_comune', '_ufficio'))
    else:
        dati_finali = comuni_base.copy()
        
    # --- 5. PULIZIA DELLE COLONNE FINALI ---
    # Creiamo la colonna Dirigente unendo Nome e Cognome
    if 'nome_resp' in dati_finali.columns and 'cogn_resp' in dati_finali.columns:
        dati_finali['nome_resp'] = dati_finali['nome_resp'].fillna('')
        dati_finali['cogn_resp'] = dati_finali['cogn_resp'].fillna('')
        dati_finali['Dirigente'] = dati_finali['nome_resp'] + ' ' + dati_finali['cogn_resp']
        dati_finali['Dirigente'] = dati_finali['Dirigente'].str.strip()
    else:
        dati_finali['Dirigente'] = "Dati uffici mancanti"

    # Selezioniamo e rinominiamo solo le colonne che ci interessano davvero
    colonne_scelte = {
        'Comune': 'Comune',
        'Provincia': 'Prov',
        'pop_res_21': 'Popolazione',
        'des_ou': 'Nome Ufficio',
        'Dirigente': 'Dirigente',
        'telefono': 'Telefono Ufficio',
        'mail1_ufficio': 'Email Ufficio',
        'mail1_comune': 'PEC Protocollo'
    }
    
    # Teniamo solo le colonne che esistono effettivamente dopo i vari incroci
    colonne_presenti = {k: v for k, v in colonne_scelte.items() if k in dati_finali.columns}
    df_pulito = dati_finali[list(colonne_presenti.keys())].rename(columns=colonne_presenti)
    
    # Puliamo i valori vuoti visivamente
    df_pulito.fillna('-', inplace=True)
    
    return df_pulito

# --- FONTE DATI 3: GEOGRAFIA DA OPENSTREETMAP (CON FIX ANTI-BLOCCO) ---
@st.cache_data
def cerca_comuni_su_arteria(codice_strada):
    overpass_url = "https://overpass-api.de/api/interpreter"
    codice_strada = codice_strada.upper().strip()
    variante_spazio = f"{codice_strada[:2]} {codice_strada[2:]}" if len(codice_strada) > 2 and codice_strada[:2].isalpha() and codice_strada[2:].isdigit() else codice_strada

    query = f"""
    [out:json][timeout:30];
    area["name"="Veneto"]->.regione;
    (
      way["ref"="{codice_strada}"](area.regione);
      way["ref"="{variante_spazio}"](area.regione);
    )->.strada;
    rel(around.strada:2000)["admin_level"="8"];
    out tags;
    """
    
    # IL TRAVESTIMENTO: Facciamo credere al server che siamo un browser Chrome per evitare l'errore 403
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        # Aggiunto il parametro headers
        risposta = requests.post(overpass_url, data={'data': query}, headers=headers, timeout=25)
        if risposta.status_code != 200:
            st.error(f"Errore {risposta.status_code} dal server cartografico. Il server potrebbe essere intasato, riprova tra qualche minuto.")
            return []
            
        dati_json = risposta.json()
        return [elemento.get('tags', {}).get('name').strip().upper() for elemento in dati_json.get('elements', []) if elemento.get('tags', {}).get('name')]
    except Exception as e:
        st.error(f"Connessione alla mappa fallita: {e}")
        return []

# --- INTERFACCIA UTENTE ---
st.write("🔄 Calcolo incroci database (Amministrazioni + Uffici + ISTAT) in corso...")
dati_base = carica_dati_completi()

if dati_base.empty:
    st.error("⚠️ Nessun dato trovato. Assicurati che amministrazioni.txt sia su GitHub.")
else:
    st.sidebar.header("Filtri di Ricerca")
    
    province_disponibili = ["Tutte"] + sorted(dati_base['Prov'].unique().tolist())
    provincia_scelta = st.sidebar.selectbox("Seleziona Provincia:", province_disponibili)
    
    strada_scelta = st.sidebar.text_input("Codice Arteria (es. SP247 o SS11):", "").strip()
    
    risultati = dati_base.copy()
    
    if provincia_scelta != "Tutte":
        risultati = risultati[risultati['Prov'] == provincia_scelta]
    
    if strada_scelta:
        with st.spinner(f"🔍 Tracciamento cartografico dell'arteria {strada_scelta}..."):
            elenco_comuni_strada = cerca_comuni_su_arteria(strada_scelta)
            
        if elenco_comuni_strada:
            risultati['Comune_Upper'] = risultati['Comune'].astype(str).str.strip().str.upper()
            risultati = risultati[risultati['Comune_Upper'].isin(elenco_comuni_strada)]
            risultati.drop(columns=['Comune_Upper'], errors='ignore', inplace=True)
            st.sidebar.success("✅ Strada individuata e comuni filtrati.")
        else:
            st.sidebar.warning(f"⚠️ Nessun comune trovato. Il server mappa potrebbe essere saturo o la sigla errata.")
    
    st.subheader("Risultati dello Scouting (Uffici Tecnici)")
    st.write(f"Uffici in target trovati: **{len(risultati)}**")
    
    if not risultati.empty:
        risultati.sort_values(by=['Prov', 'Comune'], inplace=True)
        risultati.reset_index(drop=True, inplace=True)
        st.dataframe(risultati, use_container_width=True)
        
        csv = risultati.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Scarica Report CSV", data=csv, file_name='scouting_uffici_tecnici_veneto.csv', mime='text/csv')
