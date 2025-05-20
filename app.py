import pdfplumber
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import re
from fuzzywuzzy import fuzz, process
import unicodedata

# Fecha actual del sistema
current_date = datetime.now()

def extract_date_range(text):
    """Extrae el rango de fechas del texto y genera una lista de fechas en formato YYYY-MM-DD."""
    match = re.search(r"(\d{2}/\d{2}/\d{4})-(\d{2}/\d{2}/\d{4})", text)
    if match:
        start_date = datetime.strptime(match.group(1), "%d/%m/%Y")
        end_date = datetime.strptime(match.group(2), "%d/%m/%Y")
        delta = end_date - start_date
        date_list = [start_date + timedelta(days=i) for i in range(delta.days + 1)]
        return date_list
    return None

def combine_tables(table1, table2, date_list):
    """Combina dos tablas y normaliza los encabezados."""
    headers = ["Info"] + [date.strftime("%Y-%m-%d") for date in date_list]
    data1 = table1[1:]
    data2 = table2[1:]
    combined_data = [row1 + row2[1:] for row1, row2 in zip(data1, data2)]
    return pd.DataFrame(combined_data, columns=headers[:len(table1[0]) + len(table2[0]) - 1])

def normalize_text(text):
    """Normaliza caracteres (Ñ → N, etc.), elimina espacios extra y convierte a mayúsculas."""
    if not isinstance(text, str):
        return ""
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if unicodedata.category(c) != 'Mn')
    return ' '.join(text.split()).upper()

def extract_alias(info):
    """Extrae el alias de la cadena completa."""
    return normalize_text(info.split('\n')[0].strip())

def extract_position(info):
    """Extrae la posición (COMANDANTE o COPILOTO) de la cadena completa."""
    lines = info.split('\n')
    for line in lines:
        line = normalize_text(line.strip())
        if "COMANDANTE" in line:
            return "COMANDANTE"
        elif "COPILOTO" in line:
            return "COPILOTO"
    return "DESCONOCIDO"

def format_flight_info(flight_str):
    """Procesa la cadena de vuelo para extraer el recorrido y las horas de salida/llegada."""
    if not flight_str or not isinstance(flight_str, str) or flight_str.isspace():
        return "Sin información"
    
    flight_str = flight_str.replace('#', ' ')
    parts = flight_str.split()
    if len(parts) < 2:
        return "Formato inválido"
    
    code = parts[0]
    flight_data = parts[1:]
    
    airports = []
    times = []
    for item in flight_data:
        if re.match(r'^[A-Z]{3}$', item):
            airports.append(item)
        elif re.match(r'^\d{4}$', item):
            times.append(item)
    
    if not airports or not times:
        return "Sin datos válidos"
    
    route = " - ".join(airports)
    if len(times) >= 2:
        start_time = f"{times[0][:2]}:{times[0][2:]}"
        end_time = f"{times[-1][:2]}:{times[-1][2:]}"
        return f"{route} ({start_time} - {end_time})"
    
    return route

# Inicializar session_state para el DataFrame si no existe
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()

# Interfaz de Streamlit
st.image("https://raw.githubusercontent.com/ElSabio97/SabanaChecker/main/logo.png", use_column_width=True)
st.title("Buscador de Intercambios de Vuelos")

# Permitir al usuario subir múltiples archivos PDF
uploaded_files = st.file_uploader("Sube las sábanas en PDF (puedes subir varios meses)", type="pdf", accept_multiple_files=True)

if uploaded_files and st.session_state.df.empty:
    all_tables = []
    try:
        for uploaded_file in uploaded_files:
            with pdfplumber.open(uploaded_file) as pdf:
                date_range = None
                for page in pdf.pages:
                    text = page.extract_text()
                    if text and "LISTADO CUADRANTE DE LA PROGRAMACIÓN" in text:
                        date_range = extract_date_range(text)
                        break
                
                if date_range:
                    tables = []
                    for i in range(0, len(pdf.pages), 2):
                        if i + 1 < len(pdf.pages):
                            page_even = pdf.pages[i]
                            table_even = page_even.extract_tables({
                                "vertical_strategy": "lines",
                                "horizontal_strategy": "lines"
                            })[0]
                            
                            page_odd = pdf.pages[i + 1]
                            table_odd = page_odd.extract_tables({
                                "vertical_strategy": "lines",
                                "horizontal_strategy": "lines"
                            })[0]
                            
                            if table_even and table_odd and len(table_even) > 1 and len(table_odd) > 1:
                                combined_df = combine_tables(table_even, table_odd, date_range)
                                tables.append(combined_df)
                    
                    if tables:
                        df_month = pd.concat(tables, ignore_index=True)
                        df_month['Alias'] = df_month['Info'].apply(extract_alias)
                        df_month['Position'] = df_month['Info'].apply(extract_position)
                        all_tables.append(df_month)
                    else:
                        st.warning(f"No se encontraron tablas válidas en el PDF {uploaded_file.name}.")
                else:
                    st.warning(f"No se encontró rango de fechas en el PDF {uploaded_file.name}.")

        if all_tables:
            # Normalizar Alias antes de combinar
            for df in all_tables:
                df['Alias'] = df['Alias'].apply(normalize_text)
            
            # Combinar DataFrames
            common_cols = ['Alias', 'Position', 'Info']
            date_cols_all = set()
            
            # Recolectar todas las columnas de fechas
            for df in all_tables:
                date_cols_all.update([col for col in df.columns if col not in common_cols])
            
            # Ordenar columnas de fechas cronológicamente
            date_cols_all = sorted(date_cols_all, key=lambda x: datetime.strptime(x, "%Y-%m-%d"))
            
            # Inicializar DataFrame combinado con todas las columnas de fechas
            df_combined = all_tables[0].reindex(columns=common_cols + date_cols_all)
            
            # Fusionar cada DataFrame adicional
            for df in all_tables[1:]:
                date_cols = [col for col in df.columns if col not in common_cols]
                temp_df = df[common_cols + date_cols].copy()
                temp_df = temp_df.reindex(columns=common_cols + date_cols_all)
                df_combined = pd.concat([df_combined, temp_df], ignore_index=True)
            
            # Consolidar filas por Alias
            def combine_rows(group):
                result = {}
                for col in group.columns:
                    non_null = group[col].dropna()
                    result[col] = non_null.iloc[0] if not non_null.empty else None
                return pd.Series(result)
            
            df_combined = df_combined.groupby('Alias', as_index=False).apply(combine_rows)
            
            if df_combined.empty:
                st.warning("No hay datos en los PDFs procesados.")
            else:
                st.session_state.df = df_combined
                df_combined.to_csv("output_with_alias_position.csv", index=False)
        else:
            st.warning("No se encontraron tablas válidas para combinar en los PDFs subidos.")
            st.session_state.df = pd.DataFrame()

    except Exception as e:
        st.error(f"Error al procesar los PDFs: {e}")
        st.session_state.df = pd.DataFrame()
elif not uploaded_files:
    st.info("Por favor, sube al menos una sábana para continuar.")

# Continuar con la lógica solo si hay un DataFrame válido
if not st.session_state.df.empty:
    alias_input = st.text_input("Introduce tu alias (e.g., PEDRO LUIS):", "")

    if alias_input:
        alias_normalized = normalize_text(alias_input)
        aliases_original = st.session_state.df['Alias'].tolist()
        aliases_normalized = [normalize_text(alias) for alias in aliases_original]
        matches = process.extractOne(alias_normalized, aliases_normalized, scorer=fuzz.token_sort_ratio)
        
        if matches and matches[1] >= 50:
            best_match, score = matches
            best_match_index = aliases_normalized.index(best_match)
            original_best_match = st.session_state.df['Alias'].iloc[best_match_index]
            user_row = st.session_state.df[st.session_state.df['Alias'] == original_best_match].iloc[0]
            user_position = user_row['Position']
            user_in_training = "instruccion" in normalize_text(user_row['Info']).lower()
            
            st.write(f"Coincidencia encontrada: '{original_best_match}' (Similitud: {score}%)")
            st.dataframe(user_row.to_frame().T)

            date_columns = [col for col in st.session_state.df.columns if col.startswith("202") and datetime.strptime(col, "%Y-%m-%d") > current_date]
            
            with st.form(key="search_form"):
                user_activity_dates = [col for col in date_columns if "CO" in str(user_row[col])]
                if user_activity_dates:
                    selected_date = st.selectbox(
                        "Selecciona la fecha del vuelo que quieres dar:",
                        options=user_activity_dates,
                        format_func=lambda x: x,
                        key="activity_date"
                    )
                else:
                    st.warning("No tienes vuelos con 'CO' en fechas futuras.")
                    selected_date = None

                available_dates_options = [
                    date for date in date_columns
                    if date != selected_date and (
                        "SA" in str(user_row[date]) or "LI" in str(user_row[date])
                    )
                ]
                available_dates = st.multiselect(
                    "Selecciona fechas en las que estás dispuesto a hacer el vuelo del compañero:",
                    options=available_dates_options,
                    format_func=lambda x: x,
                    key="available_dates"
                )

                search_button = st.form_submit_button(label="Buscar")

            if search_button and selected_date and available_dates:
                potential_swaps = st.session_state.df[
                    (st.session_state.df[selected_date].str.contains("SA", na=False) | 
                     st.session_state.df[selected_date].str.contains("LI", na=False)) & 
                    (st.session_state.df['Alias'] != original_best_match) & 
                    (st.session_state.df['Position'] == user_position) & 
                    (st.session_state.df['Info'].str.lower().str.contains("instruccion", na=False) == user_in_training)
                ]

                if not potential_swaps.empty:
                    sa_swaps = potential_swaps[potential_swaps[selected_date].str.contains("SA", na=False)]
                    li_swaps = potential_swaps[potential_swaps[selected_date].str.contains("LI", na=False)]

                    def prepare_table_data(df_subset):
                        candidates = []
                        for index, row in df_subset.iterrows():
                            candidate_activities = [date for date in available_dates if "CO" in str(row[date])]
                            for date in candidate_activities:
                                day = str(datetime.strptime(date, "%Y-%m-%d").day)
                                month = datetime.strptime(date, "%Y-%m-%d").strftime("%B %Y")
                                candidates.append({
                                    "Mes": month,
                                    "Día del Mes": day,
                                    "Alias": row['Alias'],
                                    "Vuelos disponibles": f"{format_flight_info(str(row[date]))}"
                                })
                        # Si no hay candidatos, devolver DataFrame vacío con columnas correctas
                        if not candidates:
                            return pd.DataFrame(columns=["Mes", "Día del Mes", "Alias", "Vuelos disponibles"]).set_index(["Mes", "Día del Mes", "Alias"])
                        return pd.DataFrame(candidates).set_index(["Mes", "Día del Mes", "Alias"])

                    if not sa_swaps.empty:
                        sa_table = prepare_table_data(sa_swaps)
                        if not sa_table.empty:
                            st.subheader(f"Compañeros con SA en {selected_date}:")
                            st.table(sa_table)
                        else:
                            st.warning(f"No hay compañeros con SA en {selected_date} con vuelos en las fechas seleccionadas.")
                    else:
                        st.warning(f"No hay compañeros con SA en {selected_date}.")

                    if not li_swaps.empty:
                        li_table = prepare_table_data(li_swaps)
                        if not li_table.empty:
                            st.subheader(f"Compañeros con LI en {selected_date}:")
                            st.table(li_table)
                        else:
                            st.warning(f"No hay compañeros con LI en {selected_date} con vuelos en las fechas seleccionadas.")
                    else:
                        st.warning(f"No hay compañeros con LI en {selected_date}.")
                else:
                    st.warning(f"No hay compañeros con 'SA' o 'LI' en {selected_date} que también estén en instrucción.")
        else:
            st.warning("No se encontró ninguna coincidencia con suficiente similitud.")
    else:
        st.write("Por favor, introduce un alias para buscar.")
