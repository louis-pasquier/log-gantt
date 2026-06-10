import sqlite3
import pandas as pd
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
            conn,
            params=[phase_id],
        )
    else:
        df = pd.read_sql_query(
            "SELECT t.id, t.name, p.name as phase, t.phase_id FROM tasks t JOIN phases p ON t.phase_id=p.id ORDER BY p.name, t.name",
            conn,
        )
    conn.close()
    return df


def add_task(phase_id, name):
    conn = sqlite3.connect(DB)
    conn.execute(
        "INSERT INTO tasks(phase_id, name) VALUES (?, ?)", (phase_id, name.strip())
    )
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
        (
            task_id,
            str(work_date),
            float(hours),
            str(week_start),
            str(week_end),
            int(milestone),
            note,
        ),
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


def update_entry_hours(entry_id, new_hour):
    conn = sqlite3.connect(DB)
    conn.execute("UPDATE entries SET hours=? WHERE id=?", (new_hour, entry_id))
    conn.commit()
    conn.close()


def update_entry_date(entry_id, new_date):
    conn = sqlite3.connect(DB)
    work_date_dt = pd.to_datetime(new_date)
    week_start = work_date_dt - pd.Timedelta(days=work_date_dt.weekday())
    week_end = week_start + pd.Timedelta(days=6)
    conn.execute(
        "UPDATE entries SET work_date=?, week_start=?, week_end=? WHERE id=?",
        (
            work_date_dt.strftime("%Y-%m-%d"),
            week_start.strftime("%Y-%m-%d"),
            week_end.strftime("%Y-%m-%d"),
            entry_id,
        ),
    )
    conn.commit()
    conn.close()


def load_entries():
    conn = sqlite3.connect(DB)
    df = pd.read_sql_query(
        """
        SELECT e.id, p.name as phase, t.name as task,
               e.work_date, e.hours, e.week_start, e.week_end, e.milestone, e.note
        FROM entries e
        JOIN tasks t ON e.task_id = t.id
        JOIN phases p ON t.phase_id = p.id
        ORDER BY e.week_start, p.name, t.name
    """,
        conn,
    )
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
        ordered.append(
            {
                "label": ph,
                "is_phase": True,
                "start": subset["real_start"].min(),
                "end": subset["real_end"].max(),
            }
        )

        task_subset = (
            subset.groupby("task")
            .agg({"real_start": "min", "real_end": "max"})
            .reset_index()
        )
        task_subset = task_subset.sort_values("real_start")

        for _, row in task_subset.iterrows():
            ordered.append(
                {
                    "label": row["task"],
                    "is_phase": False,
                    "start": row["real_start"],
                    "end": row["real_end"],
                }
            )

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
        is_monday = current_day.weekday() == 0
        v_color = (
            grid_col
            if not is_monday
            else ("rgba(255,255,255,0.3)" if dark else "rgba(0,0,0,0.3)")
        )

        fig.add_vline(
            x=current_day, line_width=0.8, line_dash="dash", line_color=v_color
        )

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

        fig.add_trace(
            go.Bar(
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
                showlegend=False,
            )
        )

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
            side="left",
        ),
        font=dict(family=font_fam, size=12, color=text_color),
    )

    return fig
