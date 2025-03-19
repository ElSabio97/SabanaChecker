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
    """Normaliza caracteres (Ñ → N, etc.) y convierte a mayúsculas."""
    return ''.join(c for c in unicodedata.normalize('NFKD', text) if unicodedata.category(c) != 'Mn').upper()

def extract_alias(info):
    """Extrae el alias de la cadena completa."""
    return info.split('\n')[0].strip()

def extract_position(info):
    """Extrae la posición (COMANDANTE o COPILOTO) de la cadena completa."""
    lines = info.split('\n')
    for line in lines:
        line = line.strip().upper()
        if "COMANDANTE" in line:
            return "COMANDANTE"
        elif "COPILOTO" in line:
            return "COPILOTO"
    return "DESCONOCIDO"

# Inicializar session_state para el DataFrame si no existe
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()

# Interfaz de Streamlit
# Mostrar el logo antes del título usando la URL raw de GitHub
st.image("https://raw.githubusercontent.com/tu_usuario/flight_swap_app/main/assets/logo_sepla.png", use_column_width=True)

st.title("Buscador de Intercambios de Vuelos")

# Permitir al usuario subir el archivo PDF
uploaded_file = st.file_uploader("Sube la sábana en pdf", type="pdf")

if uploaded_file is not None and st.session_state.df.empty:
    # Procesamiento del PDF subido
    try:
        with pdfplumber.open(uploaded_file) as pdf:
            tables = []
            date_range = None
            
            for page in pdf.pages:
                text = page.extract_text()
                if text and "LISTADO CUADRANTE DE LA PROGRAMACIÓN" in text:
                    date_range = extract_date_range(text)
                    break
            
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
                df = pd.concat(tables, ignore_index=True)
                df['Alias'] = df['Info'].apply(extract_alias)
                df['Position'] = df['Info'].apply(extract_position)
                
                if df.empty:
                    st.warning("No hay datos en el PDF procesado.")
                else:
                    st.session_state.df = df
                    df.to_csv("output_with_alias_position.csv", index=False)
            else:
                st.warning("No se encontraron tablas válidas para combinar.")
                st.session_state.df = pd.DataFrame()

    except Exception as e:
        st.error(f"Error al procesar el PDF: {e}")
        st.session_state.df = pd.DataFrame()
elif uploaded_file is None:
    st.info("Por favor, sube la sábana para continuar.")

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
            user_in_training = "instruccion" in user_row['Info'].lower()  # Verificar si el usuario está en instrucción
            
            st.write(f"Coincidencia encontrada: '{original_best_match}' (Similitud: {score}%)")
            st.dataframe(user_row.to_frame().T)

            # Filtrar fechas posteriores a la actual
            date_columns = [col for col in st.session_state.df.columns if col.startswith("2025") and datetime.strptime(col, "%Y-%m-%d") > current_date]

            # --- Lógica para intercambio de vuelos (CO) ---
            with st.form(key="search_form"):
                # Selector de fecha única (vuelo que el usuario quiere dar)
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

                # Selector de fechas múltiples (vuelos que el usuario está dispuesto a tomar)
                available_dates = st.multiselect(
                    "Selecciona fechas en las que estás dispuesto a hacer el vuelo del compañero:",
                    options=date_columns,
                    format_func=lambda x: x,
                    key="available_dates"
                )

                # Botón "Buscar" dentro del formulario
                search_button = st.form_submit_button(label="Buscar")

            # Procesar solo si se presiona "Buscar"
            if search_button and selected_date and available_dates:
                # Filtrar compañeros según "instruccion" además de "SA"/"LI" y posición
                potential_swaps = st.session_state.df[
                    (st.session_state.df[selected_date].str.contains("SA", na=False) | 
                     st.session_state.df[selected_date].str.contains("LI", na=False)) &
                    (st.session_state.df['Alias'] != original_best_match) &
                    (st.session_state.df['Position'] == user_position) &
                    (st.session_state.df['Info'].str.lower().str.contains("instruccion", na=False) == user_in_training)
                ]

                if not potential_swaps.empty:
                    swap_candidates = []
                    for index, row in potential_swaps.iterrows():
                        candidate_activities = [date for date in available_dates if "CO" in str(row[date])]
                        if candidate_activities:
                            swap_candidates.append({
                                "Alias": row['Alias'],
                                "Position": row['Position'],
                                "Available on": selected_date,
                                "Activities": {date: row[date] for date in candidate_activities}
                            })

                    if swap_candidates:
                        st.subheader("Posibles compañeros para intercambio de vuelos:")
                        for candidate in swap_candidates:
                            st.write(f"**Alias**: {candidate['Alias']}")
                            st.write(f"- Libre en: {candidate['Available on']}")
                            st.write(f"- Vuelos disponibles para cubrir:")
                            for date, activity in candidate['Activities'].items():
                                st.write(f"  - {date}: {activity}")
                            st.write("---")
                    else:
                        st.warning("No hay compañeros con vuelos en las fechas seleccionadas.")
                else:
                    st.warning(f"No hay compañeros con 'SA' o 'LI' en {selected_date} que también estén en instrucción.")

            # --- Lógica para intercambio de Imaginaria (IM) ---
            st.subheader("Intercambio de Turnos de Imaginaria (IM)")

            with st.form(key="search_form_im"):
                # Selector de fecha única (Imaginaria que el usuario quiere dar)
                user_im_dates = [col for col in date_columns if "IM" in str(user_row[col])]
                if user_im_dates:
                    selected_im_date = st.selectbox(
                        "Selecciona la fecha de tu Imaginaria que quieres dar:",
                        options=user_im_dates,
                        format_func=lambda x: x,
                        key="im_date"
                    )
                else:
                    st.warning("No tienes turnos de Imaginaria (IM) en fechas futuras.")
                    selected_im_date = None

                # Selector de fechas múltiples (Imaginaria que el usuario está dispuesto a tomar)
                available_im_dates = st.multiselect(
                    "Selecciona fechas en las que estás dispuesto a hacer la Imaginaria del compañero:",
                    options=date_columns,
                    format_func=lambda x: x,
                    key="available_im_dates"
                )

                # Botón "Buscar" dentro del formulario para Imaginaria
                search_im_button = st.form_submit_button(label="Buscar compañeros para Imaginaria")

            # Procesar solo si se presiona "Buscar" para Imaginaria
            if search_im_button and selected_im_date and available_im_dates:
                # Filtrar compañeros según "instruccion" además de "SA"/"LI" y posición
                potential_im_swaps = st.session_state.df[
                    (st.session_state.df[selected_im_date].str.contains("SA", na=False) | 
                     st.session_state.df[selected_im_date].str.contains("LI", na=False)) &
                    (st.session_state.df['Alias'] != original_best_match) &
                    (st.session_state.df['Position'] == user_position) &
                    (st.session_state.df['Info'].str.lower().str.contains("instruccion", na=False) == user_in_training)
                ]

                if not potential_im_swaps.empty:
                    im_swap_candidates = []
                    for index, row in potential_im_swaps.iterrows():
                        candidate_im_activities = [date for date in available_im_dates if "IM" in str(row[date])]
                        if candidate_im_activities:
                            im_swap_candidates.append({
                                "Alias": row['Alias'],
                                "Position": row['Position'],
                                "Available on": selected_im_date,
                                "Activities": {date: row[date] for date in candidate_im_activities}
                            })

                    if im_swap_candidates:
                        st.subheader("Posibles compañeros para intercambio de Imaginaria:")
                        for candidate in im_swap_candidates:
                            st.write(f"**Alias**: {candidate['Alias']}")
                            st.write(f"- Libre en: {candidate['Available on']}")
                            st.write(f"- Turnos de Imaginaria disponibles para cubrir:")
                            for date, activity in candidate['Activities'].items():
                                st.write(f"  - {date}: {activity}")
                            st.write("---")
                    else:
                        st.warning("No hay compañeros con Imaginaria en las fechas seleccionadas.")
                else:
                    st.warning(f"No hay compañeros con 'SA' o 'LI' en {selected_im_date} que también estén en instrucción.")
        else:
            st.warning("No se encontró ninguna coincidencia con suficiente similitud.")
    else:
        st.write("Por favor, introduce un alias para buscar.")
