import streamlit as st
import pandas as pd
import requests
import zipfile
import io

st.set_page_config(page_title="Scouting Comuni Veneti", layout="wide")
st.title("Scouting Comuni Veneti (> 6000 abitanti)")

@st.cache_data
def carica_dati_completi():
    # --- 1. LETTURA AMMINISTRAZIONI (Protocollo Generale e Sindaco) ---
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

    # --- 2. LETTURA UNITA' ORGANIZZATIVE (Uffici Tecnici) ---
    ou_df = pd.DataFrame()
    try:
        with zipfile.ZipFile("ou.zip", 'r') as z:
            file_validi = [f for f in z.namelist() if not f.startswith('__MACOSX') and not f.startswith('.')]
            if file_validi:
                with z.open(file_validi[0]) as f:
                    contenuto_grezzo = f.read()
                    
                    try:
                        testo = contenuto_grezzo.decode('utf-8-sig')
                    except UnicodeDecodeError:
                        try:
                            testo = contenuto_grezzo.decode('utf-16')
                        except UnicodeDecodeError:
                            testo = contenuto_grezzo.decode('latin1')
                            
                    ou_df = pd.read_csv(io.StringIO(testo), sep='\t', dtype=str, on_bad_lines='skip')
                    ou_df.columns = ou_df.columns.str.strip()
                    
    except Exception as e:
        st.warning(f"⚠️ Impossibile caricare gli uffici dal file ou.zip. Procedo solo con i dati dei Comuni. (Errore: {e})")

    # Filtriamo solo gli uffici tecnici
    keywords = 'TECNIC|LAVORI|PUBBLIC|EDILIZIA|PATRIMONIO|MANUTENZION|PNRR'
    if not ou_df.empty and 'des_ou' in ou_df.columns:
        uffici_tecnici = ou_df[ou_df['des_ou'].astype(str).str.contains(keywords, case=False, na=False)].copy()
    else:
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
    pa_veneto['Comune_Upper'] = pa_veneto['Comune'].astype(str).str.strip().str.upper()
    istat_grandi['Comune_Upper'] = istat_grandi['comune'].astype(str).str.strip().str.upper()
    comuni_base = pd.merge(pa_veneto, istat_grandi, on='Comune_Upper', how='inner')
    
    if not uffici_tecnici.empty and 'cod_amm' in comuni_base.columns and 'cod_amm' in uffici_tecnici.columns:
        dati_finali = pd.merge(comuni_base, uffici_tecnici, on='cod_amm', how='left', suffixes=('_comune', '_ufficio'))
    else:
        dati_finali = comuni_base.copy()

    # --- 5. COSTRUZIONE DECLARATIVA DELLE COLONNE (BLINDATA) ---
    df_pulito = pd.DataFrame()
    df_pulito['Comune'] = dati_finali['Comune'].astype(str).str.title()
    df_pulito['Prov'] = dati_finali['Provincia']
    df_pulito['Popolazione'] = dati_finali['pop_res_21']
    
    # Settore/Ufficio
    if 'des_ou' in dati_finali.columns:
        df_pulito['Settore/Ufficio'] = dati_finali['des_ou'].fillna('Non indicato')
    else:
        df_pulito['Settore/Ufficio'] = 'Dati uffici mancanti'
        
    # Dirigente Tecnico
    if 'nome_resp_ufficio' in dati_finali.columns and 'cogn_resp_ufficio' in dati_finali.columns:
        nome = dati_finali['nome_resp_ufficio'].fillna('').astype(str).str.title()
        cognome = dati_finali['cogn_resp_ufficio'].fillna('').astype(str).str.title()
        df_pulito['Dirigente Tecnico'] = (nome + ' ' + cognome).str.strip()
        df_pulito['Dirigente Tecnico'].replace('', 'Non indicato', inplace=True)
    else:
        df_pulito['Dirigente Tecnico'] = 'Non indicato'
        
    # Telefono Ufficio
    if 'telefono_ufficio' in dati_finali.columns:
        df_pulito['Telefono Ufficio'] = dati_finali['telefono_ufficio'].fillna('-')
    elif 'telefono' in dati_finali.columns:
        df_pulito['Telefono Ufficio'] = dati_finali['telefono'].fillna('-')
    else:
        df_pulito['Telefono Ufficio'] = '-'
        
    # Email Diretta
    if 'mail1_ufficio' in dati_finali.columns:
        df_pulito['Email Diretta Ufficio'] = dati_finali['mail1_ufficio'].fillna('-')
    else:
        df_pulito['Email Diretta Ufficio'] = '-'
        
    # PEC Protocollo
    if 'mail1_comune' in dati_finali.columns:
        df_pulito['PEC Protocollo Comune'] = dati_finali['mail1_comune'].fillna('-')
    elif 'mail1' in dati_finali.columns:
        df_pulito['PEC Protocollo Comune'] = dati_finali['mail1'].fillna('-')
    else:
        df_pulito['PEC Protocollo Comune'] = '-'
        
    return df_pulito

# --- FONTE DATI 3: GEOGRAFIA DA OPENSTREETMAP ---
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
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        risposta = requests.post(overpass_url, data={'data': query}, headers=headers, timeout=25)
        if risposta.status_code != 200:
            st.error("Errore server cartografico. Riprova più tardi.")
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
    
    province_disponibili = ["Tutte"] + sorted(dati_base['Prov'].dropna().unique().tolist())
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
            st.sidebar.warning(f"⚠️ Nessun comune trovato.")
    
    st.subheader("Risultati dello Scouting (Uffici Tecnici)")
    st.write(f"Uffici in target trovati: **{len(risultati)}**")
    
    if not risultati.empty:
        risultati.sort_values(by=['Prov', 'Comune'], inplace=True)
        risultati.reset_index(drop=True, inplace=True)
        st.dataframe(risultati, use_container_width=True)
        
        csv = risultati.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Scarica Report CSV", data=csv, file_name='scouting_uffici_tecnici.csv', mime='text/csv')
