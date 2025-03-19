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
