from datetime import date, timedelta
import pandas as pd
import streamlit as st

from log_gantt import init_db, get_phases, update_phase_name, delete_phase, get_tasks, add_task, update_task_name, \
    delete_task, add_entry, load_entries, update_entry_note, delete_entry, build_gantt, add_phase


def main():
    # ─────────────────────────────────────────────────────────────────────────────
    # App
    # ─────────────────────────────────────────────────────────────────────────────

    init_db()
    st.set_page_config(page_title="Journal de bord", layout="wide")

    if "dark" not in st.session_state:
        st.session_state.dark = False

    # CSS: transparent backgrounds so Streamlit's own theme shows through
    st.markdown("""
    <style>
      [data-testid="stAppViewContainer"],
      [data-testid="stHeader"],
      section.main > div { background: transparent !important; }
      .js-plotly-plot .plotly { background: transparent !important; }
      h1,h2,h3 { font-family: Georgia, serif !important; }
      .block-container { padding-top: 1.5rem; }
      [data-baseweb="tab-list"] { gap: 8px; }
      [data-baseweb="tab"] { border-radius: 4px 4px 0 0; }
    </style>
    """, unsafe_allow_html=True)

    st.title("📋 Journal de bord & Gantt")

    tab_log, tab_gantt, tab_recap, tab_manage = st.tabs([
        "📝 Saisie", "📊 Gantt", "📈 Récapitulatif", "⚙️ Gérer phases & tâches"
    ])

    # ═══════════════════════════════════════════════════════════════
    # TAB 4 — Manage phases & tasks
    # ═══════════════════════════════════════════════════════════════
    with tab_manage:
        st.subheader("Phases")

        col_new_phase, col_spacer = st.columns([2, 3])
        with col_new_phase:
            with st.form("new_phase_form", clear_on_submit=True):
                new_phase_name = st.text_input("Nom de la nouvelle phase")
                if st.form_submit_button("➕ Créer la phase"):
                    if new_phase_name.strip():
                        ok = add_phase(new_phase_name)
                        if ok:
                            st.success(f"Phase « {new_phase_name} » créée.")
                            st.rerun()
                        else:
                            st.warning("Cette phase existe déjà.")

        phases_df = get_phases()
        if not phases_df.empty:
            show_phases = phases_df.rename(columns={"id": "ID", "name": "Phase"})
            show_phases["Delete"] = False

            # Allow editing on the "Phase" column
            edited_phases = st.data_editor(
                show_phases,
                hide_index=True,
                use_container_width=True,
                disabled=["ID"],
                key="phases_editor"
            )

            # Handle updates
            phases_editor_state = st.session_state.get("phases_editor", {})
            if phases_editor_state.get("edited_rows"):
                for row_idx, changes in st.session_state.phases_editor["edited_rows"].items():
                    if "Phase" in changes:
                        p_id = int(show_phases.iloc[row_idx]["ID"])
                        new_val = changes["Phase"]
                        update_phase_name(p_id, new_val)
                st.success("Phase modifiée.")
                st.rerun()

            # Handle deletions
            phases_to_delete = edited_phases[edited_phases["Delete"] == True]
            if not phases_to_delete.empty:
                for _, row in phases_to_delete.iterrows():
                    delete_phase(row["ID"])
                st.success("Phase(s) supprimée(s).")
                st.rerun()

        st.divider()
        st.subheader("Tâches")

        tasks_df = get_tasks()
        col_new_task, _ = st.columns([3, 2])
        with col_new_task:
            with st.form("new_task_form", clear_on_submit=True):
                if phases_df.empty:
                    st.info("Créez d'abord une phase.")
                else:
                    t_phase = st.selectbox("Phase", phases_df["id"].tolist(),
                                           format_func=lambda i: phases_df[phases_df["id"] == i]["name"].values[0])
                    t_name = st.text_input("Nom de la tâche")
                    if st.form_submit_button("➕ Créer la tâche"):
                        if t_name.strip():
                            add_task(t_phase, t_name)
                            st.success(f"Tâche « {t_name} » créée.")
                            st.rerun()

        if not tasks_df.empty:
            show_tasks = tasks_df[["id", "phase", "name"]].rename(
                columns={"id": "ID", "phase": "Phase", "name": "Tâche"})
            show_tasks["Delete"] = False

            # Allow editing on the "Tâche" column
            edited_tasks = st.data_editor(
                show_tasks,
                hide_index=True,
                use_container_width=True,
                disabled=["ID", "Phase"],
                key="tasks_editor"
            )

            # Handle updates
            task_editor_state = st.session_state.get("tasks_editor", {})
            if task_editor_state.get("edited_rows"):
                for row_idx, changes in st.session_state.tasks_editor["edited_rows"].items():
                    if "Tâche" in changes:
                        t_id = int(show_tasks.iloc[row_idx]["ID"])
                        new_val = changes["Tâche"]
                        update_task_name(t_id, new_val)
                st.success("Tâche modifiée.")
                st.rerun()

            # Handle deletions
            tasks_to_delete = edited_tasks[edited_tasks["Delete"] == True]
            if not tasks_to_delete.empty:
                for _, row in tasks_to_delete.iterrows():
                    delete_task(row["ID"])
                st.success("Tâche(s) supprimée(s).")
                st.rerun()

    # ═══════════════════════════════════════════════════════════════
    # TAB 1 — Log entry
    # ═══════════════════════════════════════════════════════════════
    with tab_log:
        phases_df = get_phases()
        tasks_df = get_tasks()

        if phases_df.empty or tasks_df.empty:
            st.info(
                "Allez dans **⚙️ Gérer phases & tâches** pour créer vos phases et tâches avant de saisir des entrées.")
        else:
            with st.form("entry_form", clear_on_submit=True):
                selected_task_id = st.selectbox(
                    "Tâche",
                    tasks_df["id"].tolist(),
                    format_func=lambda
                        i: f"{tasks_df[tasks_df['id'] == i]['phase'].values[0]} › {tasks_df[tasks_df['id'] == i]['name'].values[0]}",
                    key="entry_task"
                )

                today = date.today()

                c1, c2 = st.columns(2)
                work_date = c1.date_input("Date de travail", value=today)
                hours = c2.number_input("Heures", min_value=0.25, step=0.25, value=1.0)

                note = st.text_input("Note (optionnel)")

                submitted = st.form_submit_button("✅ Enregistrer", use_container_width=True)
                if submitted:
                    if selected_task_id is None:
                        st.warning("Sélectionnez une tâche valide.")
                    else:
                        ws = work_date - timedelta(days=work_date.weekday())
                        we = ws
                        add_entry(selected_task_id, work_date, hours, ws, we, 0, note)
                        st.success("Entrée enregistrée ✓")
                        st.rerun()

        st.divider()
        st.subheader("Historique des saisies")
        df = load_entries()
        if not df.empty:
            disp = df.copy()
            show_df = disp[["id", "phase", "task", "work_date", "hours", "note"]].rename(
                columns={"id": "ID", "phase": "Phase", "task": "Tâche", "work_date": "Date", "hours": "Heures",
                         "note": "Note"}
            )
            show_df["Delete"] = False

            # Allow editing on the "Note" column
            edited_df = st.data_editor(
                show_df,
                hide_index=True,
                use_container_width=True,
                disabled=["ID", "Phase", "Tâche", "Date", "Heures"],
                key="entry_editor"
            )

            # Handle updates
            entry_editor_state = st.session_state.get("entry_editor", {})
            if entry_editor_state.get("edited_rows"):
                for row_idx, changes in st.session_state.entry_editor["edited_rows"].items():
                    if "Note" in changes:
                        e_id = int(show_df.iloc[row_idx]["ID"])
                        new_val = changes["Note"]
                        update_entry_note(e_id, new_val)
                st.success("Note mise à jour.")
                st.rerun()

            # Handle deletions
            rows_to_delete = edited_df[edited_df["Delete"] == True]
            if not rows_to_delete.empty:
                for _, row in rows_to_delete.iterrows():
                    delete_entry(row["ID"])
                st.success("Entrée(s) supprimée(s).")
                st.rerun()

    # ═══════════════════════════════════════════════════════════════
    # TAB 2 — Gantt
    # ═══════════════════════════════════════════════════════════════
    with tab_gantt:
        df = load_entries()
        if df.empty:
            st.info("Ajoutez des entrées pour générer le Gantt.")
        else:
            is_dark = st.get_option("theme.base") == "dark"
            fig = build_gantt(df, dark=is_dark)
            st.plotly_chart(fig, use_container_width=True)

    # ═══════════════════════════════════════════════════════════════
    # TAB 3 — Recap
    # ═══════════════════════════════════════════════════════════════
    with tab_recap:
        df = load_entries()
        if df.empty:
            st.info("Aucune donnée à résumer.")
        else:
            total = df["hours"].sum()
            col1, col2, col3 = st.columns(3)
            col1.metric("Total heures", f"{total:.2f} h")
            col2.metric("Phases", df["phase"].nunique())
            col3.metric("Tâches", df["task"].nunique())

            st.divider()

            # By phase
            st.subheader("Par phase")
            phase_recap = (
                df.groupby("phase")
                .agg(
                    Heures=("hours", "sum"),
                    Entrées=("id", "count"),
                    Début=("work_date", "min"),
                    Fin=("work_date", "max"),
                )
                .reset_index()
                .rename(columns={"phase": "Phase"})
                .sort_values("Heures", ascending=False)
            )
            phase_recap["%"] = (phase_recap["Heures"] / total * 100).round(1).astype(str) + " %"
            st.dataframe(phase_recap, hide_index=True, use_container_width=True)

            st.divider()

            # By phase → task
            st.subheader("Par phase › tâche")
            task_recap = (
                df.groupby(["phase", "task"])
                .agg(
                    Heures=("hours", "sum"),
                    Entrées=("id", "count"),
                )
                .reset_index()
                .rename(columns={"phase": "Phase", "task": "Tâche"})
                .sort_values(["Phase", "Heures"], ascending=[True, False])
            )
            task_recap["%"] = (task_recap["Heures"] / total * 100).round(1).astype(str) + " %"
            st.dataframe(task_recap, hide_index=True, use_container_width=True)

            st.divider()

            # By week
            st.subheader("Par semaine")
            df_week = df.copy()
            df_week["Semaine"] = pd.to_datetime(df_week["work_date"]).apply(
                lambda d: f"P{d.isocalendar()[1]} ({d.isocalendar()[0]})"
            )
            week_recap = (
                df_week.groupby("Semaine")
                .agg(Heures=("hours", "sum"))
                .reset_index()
                .sort_values("Semaine")
            )
            st.dataframe(week_recap, hide_index=True, use_container_width=True)


if __name__ == "__main__":
    main()
