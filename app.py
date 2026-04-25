"""
Tennis Match Tracker — Improved Version
========================================
Changes from original:
  • Button-based point entry (Ace / DF are one-tap; 1st/2nd serve then pick winner)
  • Custom dark scoreboard card with large typography
  • Plotly charts: butterfly stats, momentum, and game-dominance (all zoomable)
  • Auto-save to JSON on every point — survives page refresh
  • Resume-saved-match button on startup
  • GitHub push via REST API (no extra package)
  • Input validation (empty / duplicate names)
  • initial_server tracked for correct Undo replay
  • Server correctly alternated across set boundaries (bug fix)
  • Dead code and double-reset removed (bug fixes)
  • Faster DataFrame access (.at instead of .loc in hot loop)
  • Stats display: % values shown with %, counts as integers

Requirements (add to requirements.txt):
  streamlit>=1.32
  pandas
  numpy
  plotly
  requests
"""

import base64
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ══════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════

AUTOSAVE = "tennis_autosave.json"

COL_A       = "#C41E3A"                   # crimson
COL_B       = "#1565C0"                   # royal blue
COL_A_FILL  = "rgba(196, 30, 58, 0.18)"
COL_B_FILL  = "rgba(21, 101, 192, 0.18)"

DESCRIPTIONS = [
    "Forehand winner",
    "Backhand winner",
    "Volley winner",
    "Ace",
    "Forced error forehand",
    "Forced error backhand",
    "Unforced error forehand",
    "Unforced error backhand",
    "Volley error",
    "Double fault",
    "Other",
]

# Single source-of-truth for all session-state keys and their defaults.
DEFAULTS: dict = dict(
    match_started=False,
    finished=False,
    rows=[],
    player_A="Player A",
    player_B="Player B",
    initial_server=None,     # ← NEW: first server of the whole match
    current_server=None,
    match_type="singles",
    set_no=1,
    game_no=1,
    point_no_in_game=0,
    sets_A=0,
    sets_B=0,
    games_A=0,
    games_B=0,
    points_A=0,
    points_B=0,
    tiebreak_status="",
    tiebreak_first_server=None,
    tiebreak_point_index=0,
    serve_type=None,          # ← NEW: currently selected serve button
)

STAT_ORDER = [
    "Total pts won %",
    "First serve %",
    "1st srv pts won %",
    "2nd srv pts won %",
    "Break pts saved %",
    "Break pts converted %",
    "Net pts won %",
    "Winners",
    "Aces",
    "Unforced errors",
    "Double faults",
]


# ══════════════════════════════════════════════════════════════════════
# SCORING HELPERS
# ══════════════════════════════════════════════════════════════════════

def tennis_score(pA: int, pB: int) -> tuple[str, str]:
    m = [0, 15, 30, 40]
    if pA >= 3 and pB >= 3:
        if pA == pB:
            return "40", "40"
        return ("Ad", "40") if pA > pB else ("40", "Ad")
    return str(m[min(pA, 3)]), str(m[min(pB, 3)])


def other(p: str, a: str, b: str) -> str:
    return b if p == a else a


def tb_server(first_srv: str, a: str, b: str, idx: int) -> str:
    """Return who serves the idx-th point of a tiebreak."""
    alt = other(first_srv, a, b)
    if idx == 0:
        return first_srv
    return alt if ((idx - 1) // 2) % 2 == 0 else first_srv


# ══════════════════════════════════════════════════════════════════════
# BUILD MATCH DATAFRAME
# ══════════════════════════════════════════════════════════════════════

def build_match_df(df: pd.DataFrame, player_A: str, player_B: str) -> pd.DataFrame:
    """Annotate raw rows with running Tennis_score / Games / Sets columns."""
    d = df.copy()
    for col in ("Tennis_score_A", "Tennis_score_B"):
        d[col] = ""
    for col in ("Games_player_A", "Games_player_B", "Sets_player_A", "Sets_player_B"):
        d[col] = 0

    pA = pB = gA = gB = sA = sB = 0
    cur_set = cur_game = None

    for i in d.index:
        scorer = d.at[i, "pointscorer"]
        r_set  = d.at[i, "set_number"]
        r_game = d.at[i, "game_number"]
        tb     = d.at[i, "Tiebreak_status"] or ""

        if cur_set != r_set:
            cur_set, cur_game = r_set, None
            pA = pB = gA = gB = 0

        if tb == "":
            if cur_game != r_game:
                cur_game, pA, pB = r_game, 0, 0
            if scorer == player_A:
                pA += 1
            else:
                pB += 1
            gw = None
            if pA >= 4 and pA - pB >= 2:
                gw = player_A
            elif pB >= 4 and pB - pA >= 2:
                gw = player_B
            if gw == player_A:
                gA += 1; pA = pB = 0
            elif gw == player_B:
                gB += 1; pA = pB = 0
            sa, sb = tennis_score(pA, pB)
            d.at[i, "Tennis_score_A"], d.at[i, "Tennis_score_B"] = sa, sb
        else:
            target = 10 if tb == "super_tiebreak" else 7
            if cur_game != r_game:
                cur_game, pA, pB = r_game, 0, 0
            if scorer == player_A:
                pA += 1
            else:
                pB += 1
            d.at[i, "Tennis_score_A"] = str(pA)
            d.at[i, "Tennis_score_B"] = str(pB)
            if pA >= target and pA - pB >= 2:
                sA += 1; gA = gB = pA = pB = 0
            elif pB >= target and pB - pA >= 2:
                sB += 1; gA = gB = pA = pB = 0

        d.at[i, "Games_player_A"] = gA
        d.at[i, "Games_player_B"] = gB
        d.at[i, "Sets_player_A"]  = sA
        d.at[i, "Sets_player_B"]  = sB

    return d


# ══════════════════════════════════════════════════════════════════════
# STATISTICS
# ══════════════════════════════════════════════════════════════════════

def _pct(num: float, denom: float) -> float:
    return round(100.0 * num / denom, 1) if denom else float("nan")


def generate_stats(df_m: pd.DataFrame, name_A: str, name_B: str) -> pd.DataFrame:
    """Return a DataFrame indexed by stat name, columns = [name_A, name_B]."""
    df = df_m.copy()
    df["Tiebreak_status"] = df["Tiebreak_status"].fillna("")
    stats: dict[str, dict] = {}

    pairs = [
        (name_A, name_B, "serve_result_player_A"),
        (name_B, name_A, "serve_result_player_B"),
    ]
    for name, other_name, serve_col in pairs:
        sp    = df[df["server"] == name]
        n_srv = len(sp)
        f_pts = sp[sp[serve_col].isin(["first_serve", "ace"])]
        s_pts = sp[sp[serve_col] == "second_serve"]

        winners = (
            df["description"].str.contains("winner", case=False, na=False)
            & (df["pointscorer"] == name)
            & ~df["description"].str.contains("ace", case=False, na=False)
        ).sum()

        # Unforced errors committed by `name` = points where UE desc AND other won
        ufe = (
            df["description"].str.contains("unforced error", case=False, na=False)
            & (df["pointscorer"] == other_name)
        ).sum()

        # Net approach points (FIX: removed dead-code line; logic preserved)
        net_played = net_won = 0
        for _, row in df.iterrows():
            desc   = str(row.get("description", "")).lower()
            scorer = row["pointscorer"]
            if "volley winner" in desc:
                net_player, won = scorer, True
            elif "volley error" in desc:
                # Person who made the error = the one who lost the point
                net_player, won = other(scorer, name_A, name_B), False
            else:
                continue
            if net_player == name:
                net_played += 1
                if won:
                    net_won += 1

        total_won = (df["pointscorer"] == name).sum()

        stats[name] = {
            "Total pts won %":    _pct(total_won, len(df)),
            "First serve %":      _pct(len(f_pts), n_srv),
            "1st srv pts won %":  _pct((f_pts["pointscorer"] == name).sum(), len(f_pts)),
            "2nd srv pts won %":  _pct((s_pts["pointscorer"] == name).sum(), len(s_pts)),
            "Aces":               int(sp[serve_col].eq("ace").sum()),
            "Double faults":      int(sp[serve_col].eq("double_fault").sum()),
            "Winners":            int(winners),
            "Unforced errors":    int(ufe),
            "Net pts won %":      _pct(net_won, net_played),
            "Break pts saved %":     float("nan"),
            "Break pts converted %": float("nan"),
        }

    # ── Break points (requires point-by-point game walk) ──────────────
    bp = {n: {"faced": 0, "saved": 0, "chances": 0, "converted": 0}
          for n in [name_A, name_B]}
    normal = df[df["Tiebreak_status"] == ""]
    for _, game in normal.groupby(["set_number", "game_number", "server"], sort=True):
        game = game.sort_values("point_number_in_game")
        srv  = game["server"].iloc[0]
        rec  = other(srv, name_A, name_B)
        ps = pr = 0
        for _, row in game.iterrows():
            is_bp = pr >= 3 and pr > ps
            if is_bp:
                bp[srv]["faced"]   += 1
                bp[rec]["chances"] += 1
            scorer = row["pointscorer"]
            if scorer == srv:
                ps += 1
            else:
                pr += 1
            gw = None
            if ps >= 4 and ps - pr >= 2:
                gw = srv
            elif pr >= 4 and pr - ps >= 2:
                gw = rec
            if is_bp and gw == srv:
                bp[srv]["saved"]     += 1
            if is_bp and gw == rec:
                bp[rec]["converted"] += 1
            if gw:
                break

    for name in [name_A, name_B]:
        stats[name]["Break pts saved %"]     = _pct(bp[name]["saved"],     bp[name]["faced"])
        stats[name]["Break pts converted %"] = _pct(bp[name]["converted"], bp[name]["chances"])

    return pd.DataFrame(stats)


def format_stats_for_display(stats: pd.DataFrame) -> pd.DataFrame:
    """Return a string-formatted copy of the stats DataFrame."""
    disp = stats.copy().astype(object)
    for idx in disp.index:
        for col in disp.columns:
            v = stats.at[idx, col]
            if pd.isna(v):
                disp.at[idx, col] = "—"
            elif "%" in idx:
                disp.at[idx, col] = f"{float(v):.1f}%"
            else:
                disp.at[idx, col] = str(int(float(v)))
    return disp


# ══════════════════════════════════════════════════════════════════════
# PLOTLY CHARTS  (all charts use transparent backgrounds so they
#                 inherit whatever Streamlit theme the user has set)
# ══════════════════════════════════════════════════════════════════════

_LAYOUT_BASE = dict(
    plot_bgcolor  = "rgba(0,0,0,0)",
    paper_bgcolor = "rgba(0,0,0,0)",
    font          = dict(size=13),
    margin        = dict(l=10, r=10, t=60, b=10),
)


def chart_butterfly(stats: pd.DataFrame) -> go.Figure:
    """Horizontal butterfly chart comparing stats side-by-side."""
    labels = [s for s in STAT_ORDER if s in stats.index]
    cols = stats.columns.tolist()
    vA = pd.to_numeric(stats.loc[labels, cols[0]], errors="coerce").fillna(0).values.astype(float)
    vB = pd.to_numeric(stats.loc[labels, cols[1]], errors="coerce").fillna(0).values.astype(float)
    mx = np.maximum(np.abs(vA), np.abs(vB))
    mx[mx == 0] = 1
    nA, nB = vA / mx, vB / mx

    def _fmt(v: float) -> str:
        return f"{int(v)}" if float(v) == int(float(v)) else f"{v:.1f}"

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=-nA, orientation="h", name=cols[0],
        marker_color=COL_A,
        customdata=[[_fmt(v)] for v in vA],
        hovertemplate="%{customdata[0]}<extra>" + cols[0] + "</extra>",
    ))
    fig.add_trace(go.Bar(
        y=labels, x=nB, orientation="h", name=cols[1],
        marker_color=COL_B,
        customdata=[[_fmt(v)] for v in vB],
        hovertemplate="%{customdata[0]}<extra>" + cols[1] + "</extra>",
    ))
    fig.update_layout(
        **_LAYOUT_BASE,
        title="Match Statistics Comparison",
        barmode="overlay",
        height=480,
        xaxis=dict(
            showticklabels=False, showgrid=False,
            zeroline=True, zerolinecolor="#666",
            range=[-1.55, 1.55],
        ),
        yaxis=dict(autorange="reversed"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
    )
    return fig


def chart_momentum(df_m: pd.DataFrame, name_A: str, name_B: str) -> go.Figure:
    """Filled area chart showing cumulative point lead over the match."""
    df = df_m.copy()
    df["delta"] = df["pointscorer"].map({name_A: 1, name_B: -1})
    df["cum"]   = df["delta"].cumsum()
    df["n"]     = range(1, len(df) + 1)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["n"], y=df["cum"].clip(lower=0),
        fill="tozeroy", fillcolor=COL_A_FILL,
        line=dict(color=COL_A, width=2), name=name_A,
        hovertemplate="Point %{x}: lead = %{y:+d}<extra>" + name_A + "</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df["n"], y=df["cum"].clip(upper=0),
        fill="tozeroy", fillcolor=COL_B_FILL,
        line=dict(color=COL_B, width=2), name=name_B,
        hovertemplate="Point %{x}: lead = %{y:+d}<extra>" + name_B + "</extra>",
    ))
    fig.add_hline(y=0, line_color="#888", line_width=1)
    fig.update_layout(
        **_LAYOUT_BASE,
        title="Point Momentum",
        height=320,
        xaxis=dict(title="Point #"),
        yaxis=dict(title="Cumulative point lead"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        margin=dict(l=10, r=10, t=60, b=40),
    )
    return fig


def chart_dominance(df_m: pd.DataFrame, name_A: str, name_B: str) -> go.Figure:
    """Bar chart: per-game signed win-ratio (positive = A dominant)."""
    df = df_m.copy()
    df["Tiebreak_status"] = df["Tiebreak_status"].fillna("")

    games = (
        df.groupby(["set_number", "game_number"])
        .agg(
            n  = ("pointscorer", "size"),
            nA = ("pointscorer", lambda x: (x == name_A).sum()),
            nB = ("pointscorer", lambda x: (x == name_B).sum()),
            tb = ("Tiebreak_status", "last"),
            gA = ("Games_player_A", "last"),
            gB = ("Games_player_B", "last"),
        )
        .reset_index()
    )
    games["dom"] = (games["nA"] - games["nB"]) / games["n"].clip(lower=1)

    x_labels: list[str] = []
    ys: list[float]     = []
    cs: list[str]       = []
    annotations: list   = []

    x = 0
    for sno in sorted(games["set_number"].unique()):
        sg = games[games["set_number"] == sno]
        set_start_label: str | None = None
        for _, row in sg.iterrows():
            lbl = f"S{int(sno)}G{int(row['game_number'])}"
            if set_start_label is None:
                set_start_label = lbl
            x_labels.append(lbl)
            ys.append(row["dom"])
            cs.append(COL_A if row["dom"] >= 0 else COL_B)
            x += 1
        fr = sg.iloc[-1]
        tb_str = ""
        if fr["tb"] in ("tiebreak", "super_tiebreak"):
            tb_str = f" (TB {int(fr['nA'])}-{int(fr['nB'])})"
        annotations.append(dict(
            x=set_start_label, y=1.22, xref="x", yref="y",
            text=f"Set {int(sno)}: {int(fr['gA'])}-{int(fr['gB'])}{tb_str}",
            showarrow=False, font=dict(size=11),
            xanchor="left",
        ))

    fig = go.Figure(go.Bar(
        x=x_labels, y=ys, marker_color=cs,
        hovertemplate="Game: %{x}<br>Dominance: %{y:.0%}<extra></extra>",
    ))
    fig.add_hline(y=0, line_color="#888", line_width=1)
    fig.update_layout(
        **_LAYOUT_BASE,
        title=f"Game Dominance  (↑ favours {name_A} · ↓ favours {name_B})",
        annotations=annotations,
        height=400,
        xaxis=dict(title="Game", tickangle=45),
        yaxis=dict(range=[-1.15, 1.35]),
        showlegend=False,
        margin=dict(l=10, r=10, t=70, b=70),
    )
    return fig


# ══════════════════════════════════════════════════════════════════════
# STATE MANAGEMENT
# ══════════════════════════════════════════════════════════════════════

def init_state() -> None:
    for k, v in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_state() -> None:
    """Reset ALL match state to defaults (called once, not twice)."""
    for k, v in DEFAULTS.items():
        st.session_state[k] = v


def autosave() -> None:
    """Persist full session state to a local JSON file."""
    try:
        data = {k: st.session_state.get(k, v) for k, v in DEFAULTS.items()}
        with open(AUTOSAVE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def autoload() -> bool:
    """Load previously saved match from JSON file. Returns True on success."""
    try:
        with open(AUTOSAVE, encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            if k in DEFAULTS:
                st.session_state[k] = v
        return True
    except Exception:
        return False


def push_to_github(
    token: str,
    repo: str,
    path: str,
    csv_bytes: bytes,
    commit_msg: str | None = None,
) -> tuple[bool, str]:
    """
    Push csv_bytes to {repo}/{path} via the GitHub Contents API.
    Returns (success, error_message).
    NOTE: In production, store the token in st.secrets, not the UI.
    """
    try:
        import requests as _req
    except ImportError:
        return False, "'requests' library not installed."

    if not commit_msg:
        commit_msg = f"Tennis data — {datetime.now():%Y-%m-%d %H:%M}"

    url  = f"https://api.github.com/repos/{repo}/contents/{path}"
    hdrs = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    # Fetch existing file SHA (required for updates)
    sha: str | None = None
    r = _req.get(url, headers=hdrs, timeout=10)
    if r.status_code == 200:
        sha = r.json().get("sha")

    payload: dict = {
        "message": commit_msg,
        "content": base64.b64encode(csv_bytes).decode(),
    }
    if sha:
        payload["sha"] = sha

    r = _req.put(url, headers=hdrs, json=payload, timeout=15)
    ok = r.status_code in (200, 201)
    err = "" if ok else r.json().get("message", "Unknown GitHub error")
    return ok, err


# ══════════════════════════════════════════════════════════════════════
# GAME LOGIC
# ══════════════════════════════════════════════════════════════════════

def current_server_now() -> str:
    s = st.session_state
    if s.tiebreak_status:
        return tb_server(
            s.tiebreak_first_server, s.player_A, s.player_B,
            s.tiebreak_point_index,
        )
    return s.current_server


def add_point(scorer: str, description: str, serve_result: str) -> None:
    s   = st.session_state
    a, b = s.player_A, s.player_B
    srv  = current_server_now()

    s.point_no_in_game += 1
    s.rows.append({
        "description":           description,
        "pointscorer":           scorer,
        "server":                srv,
        "serve_result_player_A": serve_result if srv == a else "",
        "serve_result_player_B": serve_result if srv == b else "",
        "set_number":            s.set_no,
        "game_number":           s.game_no,
        "point_number_in_game":  s.point_no_in_game,
        "Tiebreak_status":       s.tiebreak_status,
    })

    if s.tiebreak_status == "":
        _game_point(scorer, srv, a, b)
    else:
        _tb_point(scorer, a, b)

    s.serve_type = None   # reset serve-button selection
    autosave()


def _game_point(scorer: str, srv: str, a: str, b: str) -> None:
    s = st.session_state
    if scorer == a:
        s.points_A += 1
    else:
        s.points_B += 1

    pA, pB = s.points_A, s.points_B
    gw = None
    if pA >= 4 and pA - pB >= 2:
        gw = a
    elif pB >= 4 and pB - pA >= 2:
        gw = b

    if gw is not None:
        if gw == a:
            s.games_A += 1
        else:
            s.games_B += 1
        s.points_A = s.points_B = s.point_no_in_game = 0
        _after_game(srv, a, b)


def _after_game(last_server: str, a: str, b: str) -> None:
    """Handle set win, tiebreak trigger, or simple game advance."""
    s   = st.session_state
    gA, gB = s.games_A, s.games_B

    # ── Set won via regular game ───────────────────────────────────
    if (gA >= 6 and gA - gB >= 2) or (gB >= 6 and gB - gA >= 2):
        if gA > gB:
            s.sets_A += 1
        else:
            s.sets_B += 1
        if s.sets_A == 2 or s.sets_B == 2:
            s.finished = True
            return
        s.set_no  += 1
        s.game_no  = 1
        s.games_A  = s.games_B = 0
        # FIX: alternate server into new set (was missing in original)
        s.current_server = other(last_server, a, b)

    # ── Tiebreak / super-tiebreak ──────────────────────────────────
    elif gA == 6 and gB == 6:
        is_super = s.match_type == "doubles" and s.set_no == 3
        s.tiebreak_status       = "super_tiebreak" if is_super else "tiebreak"
        s.tiebreak_first_server = other(last_server, a, b)
        s.tiebreak_point_index  = 0
        s.point_no_in_game      = 0
        s.game_no               = 1 if is_super else 13

    # ── Normal game advance ────────────────────────────────────────
    else:
        s.current_server = other(last_server, a, b)
        s.game_no += 1


def _tb_point(scorer: str, a: str, b: str) -> None:
    s      = st.session_state
    target = 10 if s.tiebreak_status == "super_tiebreak" else 7

    if scorer == a:
        s.points_A += 1
    else:
        s.points_B += 1
    s.tiebreak_point_index += 1

    pA, pB = s.points_A, s.points_B
    tbw = None
    if pA >= target and pA - pB >= 2:
        tbw = a
    elif pB >= target and pB - pA >= 2:
        tbw = b

    if tbw is not None:
        if tbw == a:
            s.sets_A += 1
        else:
            s.sets_B += 1
        first_tb_srv = s.tiebreak_first_server
        s.points_A = s.points_B = s.point_no_in_game = 0
        s.tiebreak_status       = ""
        s.tiebreak_first_server = None
        s.tiebreak_point_index  = 0
        # After TB, the tiebreak receiver serves G1 of next set
        s.current_server = other(first_tb_srv, a, b)
        if s.sets_A == 2 or s.sets_B == 2:
            s.finished = True
            return
        s.set_no  += 1
        s.game_no  = 1
        s.games_A  = s.games_B = 0


def undo_last() -> None:
    """
    Remove the most recent point and replay all remaining rows from scratch.
    FIX: single reset call; uses initial_server for correct replay.
    """
    s = st.session_state
    if not s.rows:
        return
    saved  = s.rows[:-1]
    a, b   = s.player_A, s.player_B
    ini    = s.initial_server
    mtype  = s.match_type

    reset_state()                     # ← called ONCE (was called twice before)
    s.player_A       = a
    s.player_B       = b
    s.initial_server = ini
    s.current_server = ini
    s.match_type     = mtype
    s.match_started  = True

    for row in saved:
        sr = row["serve_result_player_A"] or row["serve_result_player_B"]
        add_point(row["pointscorer"], row["description"], sr)

    autosave()


# ══════════════════════════════════════════════════════════════════════
# UI COMPONENTS
# ══════════════════════════════════════════════════════════════════════

_SCOREBOARD_CSS = """
<style>
.scoreboard {
    background: linear-gradient(155deg, #0c1824 0%, #182638 100%);
    border-radius: 20px;
    padding: 22px 28px 18px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.55);
    margin-bottom: 20px;
    font-family: 'Trebuchet MS', 'Segoe UI', sans-serif;
    user-select: none;
}
.sb-col-header {
    display: flex;
    justify-content: flex-end;
    gap: 28px;
    font-size: 10px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #5a8db0;
    margin-bottom: 14px;
    padding-right: 4px;
}
.sb-col-header .ph { min-width: 52px; text-align: right; }
.sb-row {
    display: flex;
    align-items: center;
    margin: 4px 0;
}
.sb-name {
    flex: 1;
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 0.3px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.sb-nums {
    display: flex;
    gap: 28px;
    align-items: baseline;
}
.sb-sets, .sb-games {
    font-size: 30px;
    font-weight: 800;
    color: #dde4ee;
    min-width: 28px;
    text-align: center;
}
.sb-pts {
    font-size: 54px;
    font-weight: 900;
    line-height: 1;
    min-width: 52px;
    text-align: right;
}
.sb-divider {
    border: none;
    border-top: 1px solid rgba(255,255,255,0.07);
    margin: 6px 0;
}
.sb-ball { margin-left: 7px; font-size: 15px; }
</style>
"""


def render_scoreboard() -> None:
    s   = st.session_state
    a, b = s.player_A, s.player_B
    tb   = s.tiebreak_status
    srv  = current_server_now()

    if tb:
        sA, sB = str(s.points_A), str(s.points_B)
        lbl = "Tiebreak" if tb == "tiebreak" else "Super TB"
    else:
        sA, sB = tennis_score(s.points_A, s.points_B)
        lbl = "Points"

    ba = '<span class="sb-ball">🎾</span>' if srv == a else ""
    bb = '<span class="sb-ball">🎾</span>' if srv == b else ""

    st.markdown(_SCOREBOARD_CSS + f"""
    <div class="scoreboard">
      <div class="sb-col-header">
        <span>Sets</span>
        <span>Games</span>
        <span class="ph">{lbl}</span>
      </div>
      <div class="sb-row">
        <div class="sb-name" style="color:{COL_A}">{a}{ba}</div>
        <div class="sb-nums">
          <span class="sb-sets">{s.sets_A}</span>
          <span class="sb-games">{s.games_A}</span>
          <span class="sb-pts" style="color:{COL_A}">{sA}</span>
        </div>
      </div>
      <hr class="sb-divider">
      <div class="sb-row">
        <div class="sb-name" style="color:{COL_B}">{b}{bb}</div>
        <div class="sb-nums">
          <span class="sb-sets">{s.sets_B}</span>
          <span class="sb-games">{s.games_B}</span>
          <span class="sb-pts" style="color:{COL_B}">{sB}</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def render_point_entry() -> None:
    """
    Two-step button UI:
      Step 1 — always visible: [1st Serve] [2nd Serve] [⚡ Ace] [❌ Double Fault]
               Ace and Double Fault are one-tap and auto-assign the scorer.
      Step 2 — appears after 1st/2nd Serve selected:
               Description dropdown + [Player A wins] [Player B wins] buttons.
    """
    s    = st.session_state
    a, b = s.player_A, s.player_B
    srv  = current_server_now()
    rec  = other(srv, a, b)

    st.markdown("#### 🎯 Log a Point")
    st.markdown("**Step 1 — Serve type** *(tap to select)*")

    c1, c2, c3, c4 = st.columns(4)
    serve_buttons = [
        (c1, "🟢 1st Serve",    "first_serve"),
        (c2, "🟡 2nd Serve",    "second_serve"),
        (c3, "⚡ Ace",          "ace"),
        (c4, "❌ Double Fault", "double_fault"),
    ]
    for col, label, val in serve_buttons:
        with col:
            btn_type = "primary" if s.serve_type == val else "secondary"
            if st.button(label, key=f"sv_{val}", type=btn_type, use_container_width=True):
                if val == "ace":
                    add_point(srv, "Ace", "ace")
                    st.rerun()
                elif val == "double_fault":
                    add_point(rec, "Double fault", "double_fault")
                    st.rerun()
                else:
                    s.serve_type = val
                    st.rerun()

    # ── Step 2 ────────────────────────────────────────────────────
    if s.serve_type in ("first_serve", "second_serve"):
        st.markdown("**Step 2 — Point outcome**")

        available = [d for d in DESCRIPTIONS if d not in ("Ace", "Double fault")]
        desc = st.selectbox(
            "Description",
            available,
            key="desc_sel",
            label_visibility="collapsed",
        )

        ca, cb = st.columns(2)
        with ca:
            if st.button(
                f"🔴  {a}  wins point",
                key="win_A", type="primary", use_container_width=True,
            ):
                add_point(a, desc, s.serve_type)
                st.rerun()
        with cb:
            if st.button(
                f"🔵  {b}  wins point",
                key="win_B", type="primary", use_container_width=True,
            ):
                add_point(b, desc, s.serve_type)
                st.rerun()


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main() -> None:
    st.set_page_config(
        page_title="🎾 Tennis Tracker",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    init_state()
    s = st.session_state

    # ── Sidebar ───────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## 🎾 Tennis Tracker")
        st.markdown("---")

        if not s.match_started:
            # Restore offer
            if os.path.exists(AUTOSAVE):
                if st.button("📂 Resume saved match", use_container_width=True):
                    if autoload():
                        st.rerun()
                    else:
                        st.error("Could not load save file.")
                st.markdown("---")

            st.markdown("### Match Setup")
            player_A  = st.text_input("Player A", value=s.player_A)
            player_B  = st.text_input("Player B", value=s.player_B)
            first_srv = st.selectbox("First server", [player_A, player_B])
            mtype     = st.selectbox("Match type", ["singles", "doubles"])

            if st.button("▶️  Start Match", type="primary", use_container_width=True):
                errors = []
                if not player_A.strip():
                    errors.append("Player A name cannot be empty.")
                if not player_B.strip():
                    errors.append("Player B name cannot be empty.")
                if player_A.strip().lower() == player_B.strip().lower():
                    errors.append("Players must have different names.")
                for e in errors:
                    st.error(e)
                if not errors:
                    reset_state()
                    s.player_A       = player_A.strip()
                    s.player_B       = player_B.strip()
                    s.initial_server = first_srv
                    s.current_server = first_srv
                    s.match_type     = mtype
                    s.match_started  = True
                    autosave()
                    st.rerun()

        else:
            a, b = s.player_A, s.player_B
            st.markdown(f"**{a}** vs **{b}**")
            st.markdown(f"`{s.match_type.title()}` · Set {s.set_no}")
            st.markdown("---")

            c1, c2 = st.columns(2)
            with c1:
                if st.button(
                    "↩️ Undo", use_container_width=True,
                    disabled=not s.rows or s.finished,
                ):
                    undo_last()
                    st.rerun()
            with c2:
                if st.button("🔄 New match", use_container_width=True):
                    reset_state()
                    if os.path.exists(AUTOSAVE):
                        os.remove(AUTOSAVE)
                    st.rerun()

            # ── GitHub sync ───────────────────────────────────────
            st.markdown("---")
            st.markdown("### 🐙 GitHub Sync")
            with st.expander("Push CSV to GitHub"):
                st.caption(
                    "In production, store your token in `st.secrets` "
                    "rather than typing it here."
                )
                gh_token  = st.text_input("Personal access token", type="password")
                gh_repo   = st.text_input("Repository", placeholder="username/repo")
                gh_path   = st.text_input("File path in repo", placeholder="data/match.csv")
                gh_commit = st.text_input("Commit message", placeholder="Auto-generated if blank")

                if st.button("⬆️  Push to GitHub", use_container_width=True):
                    if not s.rows:
                        st.warning("No data yet.")
                    elif not all([gh_token, gh_repo, gh_path]):
                        st.error("Fill in token, repository, and file path.")
                    else:
                        with st.spinner("Pushing…"):
                            df_raw = pd.DataFrame(s.rows)
                            df_ann = build_match_df(df_raw, a, b)
                            ok, err = push_to_github(
                                gh_token, gh_repo, gh_path,
                                df_ann.to_csv(index=False).encode(),
                                commit_msg=gh_commit or None,
                            )
                        if ok:
                            st.success(f"✅ Pushed to `{gh_repo}/{gh_path}`")
                        else:
                            st.error(f"❌ {err}")

    # ── Welcome screen ────────────────────────────────────────────
    if not s.match_started:
        st.markdown("""
        <div style="text-align:center;padding:80px 20px;">
          <div style="font-size:88px;margin-bottom:20px">🎾</div>
          <h1 style="font-size:2.8rem;margin-bottom:12px">Tennis Match Tracker</h1>
          <p style="font-size:1.15rem;color:#666;max-width:460px;margin:0 auto">
            Enter player names in the sidebar and tap
            <strong>Start Match</strong> to begin live point tracking.
          </p>
        </div>
        """, unsafe_allow_html=True)
        return

    a, b = s.player_A, s.player_B

    if s.finished:
        winner = a if s.sets_A > s.sets_B else b
        st.success(
            f"🏆 Match complete — **{winner}** wins "
            f"({s.sets_A}–{s.sets_B} in sets)"
        )

    # ── Two-column layout ─────────────────────────────────────────
    left_col, right_col = st.columns([1, 1], gap="large")

    # Left: live scoreboard + point entry
    with left_col:
        render_scoreboard()

        if not s.finished:
            render_point_entry()
        else:
            st.info("Match finished. Use **↩️ Undo** to correct the last point, or **🔄 New match** to start over.")

        if s.rows:
            df_raw = pd.DataFrame(s.rows)
            df_ann = build_match_df(df_raw, a, b)
            ts     = datetime.now().strftime("%Y%m%d_%H%M")
            st.download_button(
                "⬇️ Download CSV",
                data=df_ann.to_csv(index=False).encode(),
                file_name=f"tennis_{a}_vs_{b}_{ts}.csv",
                mime="text/csv",
                use_container_width=True,
            )

    # Right: stats / charts / log (only when data exists)
    with right_col:
        if not s.rows:
            st.markdown("""
            <div style="text-align:center;padding:60px 20px;color:#999;">
              <div style="font-size:52px;margin-bottom:14px">📊</div>
              <p>Statistics and charts will appear here after you log your first point.</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            df_raw = pd.DataFrame(s.rows)
            df_ann = build_match_df(df_raw, a, b)
            stats  = generate_stats(df_ann, a, b)

            tab1, tab2, tab3 = st.tabs(["📊 Statistics", "📈 Charts", "📋 Point Log"])

            with tab1:
                st.dataframe(
                    format_stats_for_display(stats),
                    use_container_width=True,
                )

            with tab2:
                st.plotly_chart(chart_butterfly(stats),         use_container_width=True)
                st.plotly_chart(chart_momentum(df_ann, a, b),   use_container_width=True)
                st.plotly_chart(chart_dominance(df_ann, a, b),  use_container_width=True)

            with tab3:
                st.dataframe(df_ann, use_container_width=True)


if __name__ == "__main__":
    main()