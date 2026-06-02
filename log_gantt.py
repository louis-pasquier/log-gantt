import sqlite3
from datetime import date, timedelta
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

DB = "timesheet.db"


# ─────────────────────────────────────────────────────────────────────────────
# DB
# ─────────────────────────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # Phases table
    c.execute("""
        CREATE TABLE IF NOT EXISTS phases (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name  TEXT NOT NULL UNIQUE
        )
    """)

    # Tasks table (linked to a phase)
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            phase_id INTEGER NOT NULL REFERENCES phases(id),
            name     TEXT NOT NULL
        )
    """)

    # Time log entries
    c.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id    INTEGER NOT NULL REFERENCES tasks(id),
            work_date  TEXT NOT NULL,
            hours      REAL NOT NULL DEFAULT 0,
            week_start TEXT NOT NULL,
            week_end   TEXT NOT NULL,
            milestone  INTEGER NOT NULL DEFAULT 0,
            note       TEXT NOT NULL DEFAULT ''
        )
    """)

    conn.commit()
    conn.close()


# ── phases ────────────────────────────────────────────────────────────────────

def get_phases():
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query("SELECT id, name FROM phases ORDER BY name", conn)
    conn.close()
    return df


def add_phase(name):
    conn = sqlite3.connect(DB)
    try:
        conn.execute("INSERT INTO phases(name) VALUES (?)", (name.strip(),))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def delete_phase(phase_id):
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM phases WHERE id=?", (phase_id,))
    conn.commit()
    conn.close()

def update_phase_name(phase_id, new_name):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE phases SET name=? WHERE id=?", (new_name.strip(), phase_id))
    conn.commit()
    conn.close()

# ── tasks ─────────────────────────────────────────────────────────────────────

def get_tasks(phase_id=None):
    conn = sqlite3.connect(DB)
    if phase_id:
        df = pd.read_sql_query(
            "SELECT t.id, t.name, p.name as phase FROM tasks t JOIN phases p ON t.phase_id=p.id WHERE t.phase_id=? ORDER BY t.name",
            conn, params=(phase_id,)
        )
    else:
        df = pd.read_sql_query(
            "SELECT t.id, t.name, p.name as phase, t.phase_id FROM tasks t JOIN phases p ON t.phase_id=p.id ORDER BY p.name, t.name",
            conn
        )
    conn.close()
    return df


def add_task(phase_id, name):
    conn = sqlite3.connect(DB)
    conn.execute("INSERT INTO tasks(phase_id, name) VALUES (?, ?)", (phase_id, name.strip()))
    conn.commit()
    conn.close()


def delete_task(task_id):
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()

def update_task_name(task_id, new_name):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE tasks SET name=? WHERE id=?", (new_name.strip(), task_id))
    conn.commit()
    conn.close()


# ── entries ───────────────────────────────────────────────────────────────────

def add_entry(task_id, work_date, hours, week_start, week_end, milestone, note):
    conn = sqlite3.connect(DB)
    conn.execute(
        "INSERT INTO entries(task_id, work_date, hours, week_start, week_end, milestone, note) VALUES (?,?,?,?,?,?,?)",
        (task_id, str(work_date), float(hours), str(week_start), str(week_end), int(milestone), note)
    )
    conn.commit()
    conn.close()


def delete_entry(entry_id):
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM entries WHERE id=?", (entry_id,))
    conn.commit()
    conn.close()

def update_entry_note(entry_id, new_note):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE entries SET note=? WHERE id=?", (new_note.strip(), entry_id))
    conn.commit()
    conn.close()


def load_entries():
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query("""
        SELECT e.id, p.name as phase, t.name as task,
               e.work_date, e.hours, e.week_start, e.week_end, e.milestone, e.note
        FROM entries e
        JOIN tasks t ON e.task_id = t.id
        JOIN phases p ON t.phase_id = p.id
        ORDER BY e.week_start, p.name, t.name
    """, conn)
    conn.close()
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Gantt
# ─────────────────────────────────────────────────────────────────────────────

def build_gantt(df: pd.DataFrame, dark: bool):
    if df.empty:
        return go.Figure()

    # Themes & Colors
    bg = "#1e1e2e" if dark else "#ffffff"
    grid_col = "rgba(255,255,255,0.12)" if dark else "rgba(0,0,0,0.10)"
    line_black = "#ffffff" if dark else "#000000"
    line_gray = "#8888aa" if dark else "#7f7f7f"
    text_color = "#e2e2f0" if dark else "#000000"
    font_fam = "Georgia, serif"

    data = df.copy()

    # Parse real calendar dates from the user logs
    data["real_start"] = pd.to_datetime(data["work_date"])
    data["real_end"] = data["real_start"] + pd.Timedelta(days=1)

    seen_phases = []
    for _, row in data.iterrows():
        ph = row["phase"] or "Sans phase"
        if ph not in seen_phases:
            seen_phases.append(ph)

    ordered = []
    for ph in seen_phases:
        subset = data[data["phase"].fillna("Sans phase") == ph]
        ordered.append({
            "label": ph,
            "is_phase": True,
            "start": subset["real_start"].min(),
            "end": subset["real_end"].max()
        })

        task_subset = subset.groupby("task").agg({"real_start": "min", "real_end": "max"}).reset_index()
        task_subset = task_subset.sort_values("real_start")

        for _, row in task_subset.iterrows():
            ordered.append({
                "label": row["task"],
                "is_phase": False,
                "start": row["real_start"],
                "end": row["real_end"]
            })

    n = len(ordered)

    labels = []
    for o in ordered:
        if o["is_phase"]:
            labels.append(f"<b>{o['label']}</b>")
        else:
            labels.append(f"&nbsp;&nbsp;&nbsp;&nbsp;{o['label']}")

    fig = go.Figure()

    # Calculate strict timeline bounds aligned to Monday-to-Sunday boundaries
    min_date = data["real_start"].min()
    max_date = data["real_end"].max()
    start_timeline = min_date - pd.Timedelta(days=min_date.weekday())
    end_timeline = max_date + pd.Timedelta(days=(6 - max_date.weekday()))

    # Build a daily grid system + clean week labels
    tick_vals = []
    tick_texts = []

    # Loop day-by-day to build an explicit grid cell for each day
    current_day = start_timeline
    while current_day <= end_timeline:
        # Create a vertical grid line for every single day column boundary
        # Solid or slightly heavier line on Mondays to show week separations
        is_monday = (current_day.weekday() == 0)
        v_color = grid_col if not is_monday else ("rgba(255,255,255,0.3)" if dark else "rgba(0,0,0,0.3)")

        fig.add_vline(x=current_day, line_width=0.8, line_dash="dash", line_color=v_color)

        # Place the Week Name (PXX) only once per week block (centered on Wednesday)
        if current_day.weekday() == 3:
            week_num = current_day.isocalendar()[1]
            tick_vals.append(current_day)
            tick_texts.append(f"<b>P{week_num}</b>")

        current_day += pd.Timedelta(days=1)

    # Populate horizontal timeline bars
    for i, o in enumerate(ordered):
        y = n - 1 - i
        bh = 0.25 if o["is_phase"] else 0.08
        color = line_black if o["is_phase"] else line_gray

        duration_ms = (o["end"] - o["start"]).total_seconds() * 1000
        dur_days = (o["end"] - o["start"]).days

        fig.add_trace(go.Bar(
            x=[duration_ms],
            y=[y],
            base=[o["start"].strftime("%Y-%m-%d %H:%M:%S")],
            orientation="h",
            marker_color=color,
            width=bh,
            hovertemplate=(
                f"<b>{o['label']}</b><br>"
                f"Début: {o['start'].strftime('%d %b %Y')}<br>"
                f"Fin: {(o['end'] - pd.Timedelta(days=1)).strftime('%d %b %Y')}<br>"
                f"Durée: {dur_days} jour(s)<extra></extra>"
            ),
            showlegend=False
        ))

        # Horizontal row separation line
        fig.add_hline(y=y - 0.5, line_width=0.5, line_dash="dash", line_color=grid_col)

    fig.update_layout(
        barmode="overlay",
        height=max(400, n * 35 + 120),
        margin=dict(l=340, r=30, t=80, b=40),
        plot_bgcolor=bg,
        paper_bgcolor=bg,
        xaxis=dict(
            type="date",
            tickvals=tick_vals,
            ticktext=tick_texts,
            range=[start_timeline, end_timeline],
            showgrid=False,
            zeroline=False,
            side="top",
            tickfont=dict(size=13, family=font_fam, color=text_color),
        ),
        yaxis=dict(
            tickvals=list(range(n)),
            ticktext=[labels[n - 1 - i] for i in range(n)],
            tickfont=dict(size=12, family=font_fam, color=text_color),
            showgrid=False,
            zeroline=False,
            side="left"
        ),
        font=dict(family=font_fam, size=12, color=text_color),
    )

    return fig


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
        if st.session_state.phases_editor.get("edited_rows"):
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
        show_tasks = tasks_df[["id", "phase", "name"]].rename(columns={"id": "ID", "phase": "Phase", "name": "Tâche"})
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
        if st.session_state.tasks_editor.get("edited_rows"):
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
        st.info("Allez dans **⚙️ Gérer phases & tâches** pour créer vos phases et tâches avant de saisir des entrées.")
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
        if st.session_state.entry_editor.get("edited_rows"):
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