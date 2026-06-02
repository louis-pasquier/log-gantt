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

    bg       = "#1e1e2e" if dark else "#ffffff"
    grid_col = "rgba(255,255,255,0.08)" if dark else "rgba(0,0,0,0.08)"
    vline_col= "rgba(255,255,255,0.12)" if dark else "rgba(0,0,0,0.13)"
    phase_col= "#e2e2f0" if dark else "#1a1a1a"
    task_col = "#8888aa" if dark else "#888888"
    mile_col = "#60a5fa"
    tick_col = "#bbbbcc" if dark else "#333333"
    font_fam = "Georgia, serif"

    data = df.copy()
    data["week_start"] = pd.to_datetime(data["week_start"])
    data["week_end"]   = pd.to_datetime(data["week_end"]) + pd.Timedelta(days=7)

    seen_phases = []
    for _, row in data.iterrows():
        ph = row["phase"] or "Sans phase"
        if ph not in seen_phases:
            seen_phases.append(ph)

    ordered = []
    for ph in seen_phases:
        subset = data[data["phase"].fillna("Sans phase") == ph]
        ordered.append({"label": ph, "is_phase": True, "is_milestone": False,
                         "start": subset["week_start"].min(), "end": subset["week_end"].max()})
        for _, row in subset.iterrows():
            ordered.append({"label": row["task"], "is_phase": False,
                             "is_milestone": bool(row["milestone"]),
                             "start": row["week_start"], "end": row["week_end"]})

    n      = len(ordered)
    labels = [o["label"] for o in ordered]
    fig    = go.Figure()

    # vertical week lines
    grid_s = data["week_start"].min() - pd.Timedelta(days=7)
    grid_e = data["week_end"].max()   + pd.Timedelta(days=7)
    w = grid_s
    while w <= grid_e:
        fig.add_vline(x=w, line_width=1, line_dash="dot", line_color=vline_col)
        w += pd.Timedelta(weeks=1)

    for i, o in enumerate(ordered):
        y    = n - 1 - i
        bh   = 0.68 if o["is_phase"] else 0.50
        color= phase_col if o["is_phase"] else (mile_col if o["is_milestone"] else task_col)

        if o["is_milestone"]:
            fig.add_trace(go.Scatter(
                x=[o["start"]], y=[y], mode="markers",
                marker=dict(symbol="diamond", size=14, color=mile_col,
                            line=dict(color=bg, width=2)),
                hovertemplate=f"<b>{o['label']}</b><br>Jalon: {o['start'].strftime('%d %b %Y')}<extra></extra>",
                showlegend=False
            ))
        else:
            dur = (o["end"] - o["start"]).days / 7
            fig.add_trace(go.Bar(
                x=[o["end"] - o["start"]], y=[y],
                base=[o["start"]], orientation="h",
                marker_color=color, width=bh,
                hovertemplate=(
                    f"<b>{o['label']}</b><br>"
                    f"Début: {o['start'].strftime('%d %b %Y')}<br>"
                    f"Fin: {(o['end'] - pd.Timedelta(days=7)).strftime('%d %b %Y')}<br>"
                    f"Durée: {dur:.1f} sem.<extra></extra>"
                ),
                showlegend=False
            ))

    fig.update_layout(
        barmode="overlay",
        height=max(350, n * 34 + 80),
        margin=dict(l=0, r=20, t=30, b=40),
        plot_bgcolor=bg,
        paper_bgcolor=bg,
        xaxis=dict(
            type="date", tickformat="P%W", dtick="W1",
            ticklabelmode="period", showgrid=False, zeroline=False,
            tickfont=dict(size=11, family=font_fam, color=tick_col),
        ),
        yaxis=dict(
            tickvals=list(range(n)),
            ticktext=[labels[n - 1 - i] for i in range(n)],
            tickfont=dict(size=11, family=font_fam, color=tick_col),
            showgrid=True, gridcolor=grid_col, zeroline=False,
        ),
        font=dict(family=font_fam, size=12, color=tick_col),
    )
    return fig

# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

init_db()
st.set_page_config(page_title="Journal de bord", layout="wide")

# Detect dark mode via query param or session state
if "dark" not in st.session_state:
    st.session_state.dark = False

# CSS: transparent backgrounds so Streamlit's own theme shows through
st.markdown("""
<style>
  /* Let Streamlit manage the theme background — don't override it */
  [data-testid="stAppViewContainer"],
  [data-testid="stHeader"],
  section.main > div { background: transparent !important; }

  /* Plotly chart container background */
  .js-plotly-plot .plotly { background: transparent !important; }

  h1,h2,h3 { font-family: Georgia, serif !important; }
  .block-container { padding-top: 1.5rem; }

  /* Subtle tab styling */
  [data-baseweb="tab-list"] { gap: 8px; }
  [data-baseweb="tab"] { border-radius: 4px 4px 0 0; }
</style>
""", unsafe_allow_html=True)

st.title("📋 Journal de bord & Gantt")

tab_log, tab_gantt, tab_recap, tab_manage = st.tabs([
    "📝 Saisie", "📊 Gantt", "📈 Récapitulatif", "⚙️ Gérer phases & tâches"
])

# ═══════════════════════════════════════════════════════════════
# TAB 4 — Manage phases & tasks (must load first for selects)
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
        st.dataframe(phases_df.rename(columns={"id": "ID", "name": "Phase"}),
                     hide_index=True, use_container_width=True)
        with st.expander("🗑️ Supprimer une phase"):
            ph_del = st.selectbox("Phase à supprimer", phases_df["id"].tolist(),
                                  format_func=lambda i: phases_df[phases_df["id"]==i]["name"].values[0],
                                  key="del_phase")
            if st.button("Supprimer la phase", key="btn_del_phase"):
                delete_phase(ph_del)
                st.success("Phase supprimée.")
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
                                       format_func=lambda i: phases_df[phases_df["id"]==i]["name"].values[0])
                t_name  = st.text_input("Nom de la tâche")
                if st.form_submit_button("➕ Créer la tâche"):
                    if t_name.strip():
                        add_task(t_phase, t_name)
                        st.success(f"Tâche « {t_name} » créée.")
                        st.rerun()

    if not tasks_df.empty:
        st.dataframe(
            tasks_df[["id", "phase", "name"]].rename(columns={"id":"ID","phase":"Phase","name":"Tâche"}),
            hide_index=True, use_container_width=True
        )
        with st.expander("🗑️ Supprimer une tâche"):
            task_del = st.selectbox("Tâche à supprimer", tasks_df["id"].tolist(),
                                    format_func=lambda i: f"{tasks_df[tasks_df['id']==i]['phase'].values[0]} › {tasks_df[tasks_df['id']==i]['name'].values[0]}",
                                    key="del_task")
            if st.button("Supprimer la tâche", key="btn_del_task"):
                delete_task(task_del)
                st.success("Tâche supprimée.")
                st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 1 — Log entry
# ═══════════════════════════════════════════════════════════════
with tab_log:
    phases_df = get_phases()
    tasks_df  = get_tasks()

    if phases_df.empty or tasks_df.empty:
        st.info("Allez dans **⚙️ Gérer phases & tâches** pour créer vos phases et tâches avant de saisir des entrées.")
    else:
        with st.form("entry_form", clear_on_submit=True):
            c1, c2 = st.columns(2)

            selected_phase_id = c1.selectbox(
                "Phase",
                phases_df["id"].tolist(),
                format_func=lambda i: phases_df[phases_df["id"]==i]["name"].values[0],
                key="entry_phase"
            )

            phase_tasks = tasks_df[tasks_df["phase_id"] == selected_phase_id]
            if phase_tasks.empty:
                c2.warning("Aucune tâche dans cette phase.")
                selected_task_id = None
            else:
                selected_task_id = c2.selectbox(
                    "Tâche",
                    phase_tasks["id"].tolist(),
                    format_func=lambda i: phase_tasks[phase_tasks["id"]==i]["name"].values[0],
                    key="entry_task"
                )

            today       = date.today()
            this_monday = today - timedelta(days=today.weekday())

            r2c1, r2c2, r2c3, r2c4 = st.columns(4)
            work_date  = r2c1.date_input("Date de travail", value=today)
            hours      = r2c2.number_input("Heures", min_value=0.25, step=0.25, value=1.0)
            week_start = r2c3.date_input("Semaine début (Gantt)", value=this_monday)
            week_end   = r2c4.date_input("Semaine fin (Gantt)",   value=this_monday)

            note      = st.text_input("Note (optionnel)")
            milestone = st.checkbox("Jalon (milestone)")

            submitted = st.form_submit_button("✅ Enregistrer", use_container_width=True)
            if submitted:
                if selected_task_id is None:
                    st.warning("Sélectionnez une tâche valide.")
                elif week_end < week_start:
                    st.warning("La semaine de fin doit être ≥ semaine de début.")
                else:
                    ws = week_start - timedelta(days=week_start.weekday())
                    we = week_end   - timedelta(days=week_end.weekday())
                    add_entry(selected_task_id, work_date, hours, ws, we, milestone, note)
                    st.success("Entrée enregistrée ✓")
                    st.rerun()

    st.divider()
    st.subheader("Historique des saisies")
    df = load_entries()
    if not df.empty:
        disp = df.copy()
        disp["Sem. début"] = pd.to_datetime(disp["week_start"]).apply(lambda d: f"P{d.isocalendar()[1]}")
        disp["Sem. fin"]   = pd.to_datetime(disp["week_end"]).apply(lambda d: f"P{d.isocalendar()[1]}")
        disp["Jalon"]      = disp["milestone"].astype(bool)
        st.dataframe(
            disp[["id","phase","task","work_date","hours","Sem. début","Sem. fin","Jalon","note"]].rename(
                columns={"id":"ID","phase":"Phase","task":"Tâche","work_date":"Date","hours":"Heures","note":"Note"}
            ),
            hide_index=True, use_container_width=True
        )
        with st.expander("🗑️ Supprimer une entrée"):
            del_id = st.selectbox(
                "Entrée à supprimer",
                df["id"].tolist(),
                format_func=lambda i: f"#{i} – {df[df['id']==i]['task'].values[0]} ({df[df['id']==i]['work_date'].values[0]}, {df[df['id']==i]['hours'].values[0]}h)"
            )
            if st.button("Supprimer", type="secondary"):
                delete_entry(del_id)
                st.success("Entrée supprimée.")
                st.rerun()
    else:
        st.info("Aucune entrée pour l'instant.")

# ═══════════════════════════════════════════════════════════════
# TAB 2 — Gantt
# ═══════════════════════════════════════════════════════════════
with tab_gantt:
    df = load_entries()
    if df.empty:
        st.info("Ajoutez des entrées pour générer le Gantt.")
    else:
        # Detect dark mode from Streamlit theme
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

        # By phase → task (nested)
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
