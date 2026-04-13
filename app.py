import io
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

BASE_POINT_DESCRIPTIONS = [
    "forced error forehand",
    "forced error backhand",
    "unforced error forehand",
    "unforced error backhand",
    "volley winner",
    "volley error",
    "forehand winner",
    "backhand winner",
    "unknown",
]

SERVE_RESULT_OPTIONS = ["first_serve", "second_serve", "ace", "double_fault"]


def tennis_score(pA, pB):
    score_map = [0, 15, 30, 40]
    if pA >= 3 and pB >= 3:
        if pA == pB:
            return "40", "40"
        elif pA == pB + 1:
            return "A", "40"
        elif pB == pA + 1:
            return "40", "A"
    return str(score_map[min(pA, 3)]), str(score_map[min(pB, 3)])


def tiebreak_server_for_point(first_server, player_A, player_B, point_index):
    other = player_B if first_server == player_A else player_A
    if point_index == 0:
        return first_server
    block = (point_index - 1) // 2
    return other if block % 2 == 0 else first_server


def other_player(player, player_A, player_B):
    return player_B if player == player_A else player_A


def current_server_name():
    player_A = st.session_state.player_A
    player_B = st.session_state.player_B
    if st.session_state.tiebreak_status:
        return tiebreak_server_for_point(
            st.session_state.tiebreak_first_server,
            player_A,
            player_B,
            st.session_state.tiebreak_point_index,
        )
    return st.session_state.current_server


def valid_point_descriptions(server, scorer):
    descriptions = list(BASE_POINT_DESCRIPTIONS)
    if scorer == server:
        descriptions.append("ace")
    else:
        descriptions.append("double fault")
    return descriptions


def valid_serve_results(server, scorer, description):
    if description == "ace":
        return ["ace"]
    if description == "double fault":
        return ["double_fault"]

    if scorer == server:
        return ["first_serve", "second_serve"]
    return ["first_serve", "second_serve"]


def pick_valid(current_value, valid_options):
    return current_value if current_value in valid_options else valid_options[0]


def render_figure_download(fig, filename_base):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=220, bbox_inches="tight")
    buf.seek(0)
    st.download_button(
        f"Download {filename_base}.png",
        data=buf.getvalue(),
        file_name=f"{filename_base}.png",
        mime="image/png",
    )


def build_match_dataframe(df, player_A, player_B, match_type="singles"):
    df_match = df.copy()

    df_match["Score_player_A"] = df_match["pointscorer"].eq(player_A).astype(int)
    df_match["Score_player_B"] = df_match["pointscorer"].eq(player_B).astype(int)

    df_match["Tennis_score_A"] = ""
    df_match["Tennis_score_B"] = ""
    df_match["Games_player_A"] = 0
    df_match["Games_player_B"] = 0
    df_match["Sets_player_A"] = 0
    df_match["Sets_player_B"] = 0

    points_A = points_B = games_A = games_B = sets_A = sets_B = 0
    current_set = None
    current_game = None

    for i in df_match.index:
        scorer = df_match.loc[i, "pointscorer"]
        row_set = df_match.loc[i, "set_number"]
        row_game = df_match.loc[i, "game_number"]
        tb_status = df_match.loc[i, "Tiebreak_status"]

        if current_set != row_set:
            current_set = row_set
            current_game = None
            points_A = points_B = games_A = games_B = 0

        if pd.isna(tb_status) or tb_status == "":
            if current_game != row_game:
                current_game = row_game
                points_A = points_B = 0

            if scorer == player_A:
                points_A += 1
            else:
                points_B += 1

            game_winner = None
            if points_A >= 4 and points_A - points_B >= 2:
                game_winner = player_A
            elif points_B >= 4 and points_B - points_A >= 2:
                game_winner = player_B

            if game_winner == player_A:
                games_A += 1
                points_A = points_B = 0
            elif game_winner == player_B:
                games_B += 1
                points_A = points_B = 0

            score_A, score_B = tennis_score(points_A, points_B)
            df_match.loc[i, "Tennis_score_A"] = score_A
            df_match.loc[i, "Tennis_score_B"] = score_B

        elif tb_status == "tiebreak":
            if current_game != row_game:
                current_game = row_game
                points_A = points_B = 0

            if scorer == player_A:
                points_A += 1
            else:
                points_B += 1

            df_match.loc[i, "Tennis_score_A"] = str(points_A)
            df_match.loc[i, "Tennis_score_B"] = str(points_B)

            if points_A >= 7 and points_A - points_B >= 2:
                sets_A += 1
                games_A = games_B = points_A = points_B = 0
                df_match.loc[i, "Tennis_score_A"] = "0"
                df_match.loc[i, "Tennis_score_B"] = "0"
            elif points_B >= 7 and points_B - points_A >= 2:
                sets_B += 1
                games_A = games_B = points_A = points_B = 0
                df_match.loc[i, "Tennis_score_A"] = "0"
                df_match.loc[i, "Tennis_score_B"] = "0"

        elif tb_status == "super_tiebreak":
            if current_game != row_game:
                current_game = row_game
                points_A = points_B = 0

            if scorer == player_A:
                points_A += 1
            else:
                points_B += 1

            df_match.loc[i, "Tennis_score_A"] = str(points_A)
            df_match.loc[i, "Tennis_score_B"] = str(points_B)

            if points_A >= 10 and points_A - points_B >= 2:
                sets_A += 1
                points_A = points_B = 0
                df_match.loc[i, "Tennis_score_A"] = "0"
                df_match.loc[i, "Tennis_score_B"] = "0"
            elif points_B >= 10 and points_B - points_A >= 2:
                sets_B += 1
                points_A = points_B = 0
                df_match.loc[i, "Tennis_score_A"] = "0"
                df_match.loc[i, "Tennis_score_B"] = "0"

        df_match.loc[i, "Games_player_A"] = games_A
        df_match.loc[i, "Games_player_B"] = games_B
        df_match.loc[i, "Sets_player_A"] = sets_A
        df_match.loc[i, "Sets_player_B"] = sets_B

    return df_match


def generate_match_stats(df_match, player_A_name, player_B_name):
    df = df_match.copy()
    df["Tiebreak_status"] = df["Tiebreak_status"].fillna("")

    player_map = {"player A": player_A_name, "player B": player_B_name}
    players = ["player A", "player B"]

    def other_player_label(player):
        return "player B" if player == "player A" else "player A"

    stats = {}
    for player in players:
        service_points = df[df["server"] == player_map[player]].copy()
        serve_col = "serve_result_player_A" if player == "player A" else "serve_result_player_B"

        first_serves_in = service_points[serve_col].isin(["first_serve", "ace"]).sum()
        total_service_points = len(service_points)
        first_serve_points = service_points[service_points[serve_col].isin(["first_serve", "ace"])]
        second_serve_points = service_points[service_points[serve_col] == "second_serve"]
        first_serve_points_won = (first_serve_points["pointscorer"] == player_map[player]).sum()
        second_serve_points_won = (second_serve_points["pointscorer"] == player_map[player]).sum()
        aces = (service_points[serve_col] == "ace").sum()
        double_faults = (service_points[serve_col] == "double_fault").sum()
        unforced_errors_mask = df["description"].str.contains("unforced error", case=False, na=False)

        player_winners = (
            df["description"].str.contains("winner", case=False, na=False)
            & (df["pointscorer"] == player_map[player])
            & ~df["description"].str.contains("ace", case=False, na=False)
        ).sum()

        opponent_name = player_map[other_player_label(player)]
        player_unforced_errors = (unforced_errors_mask & (df["pointscorer"] == opponent_name)).sum()

        net_played = 0
        net_won = 0
        for _, row in df.iterrows():
            desc = str(row["description"]).lower()
            scorer = row["pointscorer"]
            if "volley winner" in desc:
                net_player = scorer
                won = True
            elif "volley error" in desc:
                net_player = row["pointscorer"]
                net_player = player_A_name if scorer == player_B_name else player_B_name
                won = False
            else:
                continue

            if net_player == player_map[player]:
                net_played += 1
                if won:
                    net_won += 1

        total_points_won = (df["pointscorer"] == player_map[player]).sum()

        stats[player] = {
            "First serve %": round(100 * first_serves_in / total_service_points, 1) if total_service_points else np.nan,
            "First serve points won %": round(100 * first_serve_points_won / len(first_serve_points), 1) if len(first_serve_points) else np.nan,
            "Second serve points won %": round(100 * second_serve_points_won / len(second_serve_points), 1) if len(second_serve_points) else np.nan,
            "Aces": int(aces),
            "Double faults": int(double_faults),
            "Winners": int(player_winners),
            "Unforced errors": int(player_unforced_errors),
            "Net points won %": round(100 * net_won / net_played, 1) if net_played else np.nan,
            "Total points won %": round(100 * total_points_won / len(df), 1) if len(df) else np.nan,
        }

    break_points_faced = {"player A": 0, "player B": 0}
    break_points_saved = {"player A": 0, "player B": 0}
    break_points_chances = {"player A": 0, "player B": 0}
    break_points_converted = {"player A": 0, "player B": 0}

    normal_games = df[df["Tiebreak_status"] == ""].copy()
    name_to_key = {player_A_name: "player A", player_B_name: "player B"}

    for (_, _, _), game in normal_games.groupby(["set_number", "game_number", "server"], sort=True):
        game = game.sort_values("point_number_in_game")
        server_name = game["server"].iloc[0]
        receiver_name = player_B_name if server_name == player_A_name else player_A_name
        server = name_to_key[server_name]
        receiver = name_to_key[receiver_name]
        p_server = p_receiver = 0

        for _, row in game.iterrows():
            is_break_point = (p_receiver >= 3) and (p_receiver - p_server >= 1)
            scorer = name_to_key[row["pointscorer"]]

            if is_break_point:
                break_points_faced[server] += 1
                break_points_chances[receiver] += 1
                if scorer == server:
                    break_points_saved[server] += 1
                else:
                    break_points_converted[receiver] += 1

            if scorer == server:
                p_server += 1
            else:
                p_receiver += 1

            game_over = (
                (p_server >= 4 and p_server - p_receiver >= 2)
                or (p_receiver >= 4 and p_receiver - p_server >= 2)
            )
            if game_over:
                break

    for player in players:
        stats[player]["Break points saved %"] = (
            round(100 * break_points_saved[player] / break_points_faced[player], 1)
            if break_points_faced[player] else np.nan
        )
        stats[player]["Break points converted %"] = (
            round(100 * break_points_converted[player] / break_points_chances[player], 1)
            if break_points_chances[player] else np.nan
        )

    stats_df = pd.DataFrame(stats)
    stats_df.columns = [player_A_name, player_B_name]
    return stats_df


def plot_stats_rotated(stats_df):
    df_plot = stats_df.copy()
    stat_order = [
        "Aces",
        "Double faults",
        "First serve %",
        "First serve points won %",
        "Second serve points won %",
        "Break points saved %",
        "Break points converted %",
        "Winners",
        "Unforced errors",
        "Net points won %",
        "Total points won %",
    ]
    df_plot = df_plot.loc[[s for s in stat_order if s in df_plot.index]]

    values_A = pd.to_numeric(df_plot.iloc[:, 0], errors="coerce").fillna(0).values.astype(float)
    values_B = pd.to_numeric(df_plot.iloc[:, 1], errors="coerce").fillna(0).values.astype(float)
    labels = df_plot.index.tolist()

    max_per_row = np.maximum(values_A, values_B)
    max_per_row[max_per_row == 0] = 1
    norm_A = values_A / max_per_row
    norm_B = values_B / max_per_row
    y = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(13, 9), dpi=170)
    ax.barh(y, -norm_A, height=0.62, color="crimson")
    ax.barh(y, norm_B, height=0.62, color="#003366")
    ax.axvline(0, linewidth=1)

    for i, label in enumerate(labels):
        ax.text(
            0, i, label,
            ha="center", va="center", fontsize=11,
            bbox=dict(facecolor="white", edgecolor="none", boxstyle="square,pad=0.25"),
            zorder=3,
        )

    def fmt(v):
        return f"{int(v)}" if float(v).is_integer() else f"{v:.1f}"

    offset = 0.04
    for i, (raw, norm) in enumerate(zip(values_A, norm_A)):
        if raw != 0:
            ax.text(-norm - offset, i, fmt(raw), ha="right", va="center", fontsize=10)
    for i, (raw, norm) in enumerate(zip(values_B, norm_B)):
        if raw != 0:
            ax.text(norm + offset, i, fmt(raw), ha="left", va="center", fontsize=10)

    ax.text(-0.78, -0.95, df_plot.columns[0], ha="center", va="bottom", fontsize=14, fontweight="bold")
    ax.text(0.78, -0.95, df_plot.columns[1], ha="center", va="bottom", fontsize=14, fontweight="bold")
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_xlim(-1.45, 1.45)
    ax.set_ylim(len(labels) - 0.3, -0.6)
    ax.set_title("Match Summary", fontsize=18, fontweight="bold")
    for spine in ax.spines.values():
        spine.set_visible(False)
    fig.tight_layout()
    return fig


def plot_dominance(df_match, player_A_name, player_B_name):
    df = df_match.copy()
    df["Tiebreak_status"] = df["Tiebreak_status"].fillna("")

    games = (
        df.groupby(["set_number", "game_number"])
        .agg(
            total_points=("pointscorer", "size"),
            points_A=("pointscorer", lambda x: (x == player_A_name).sum()),
            points_B=("pointscorer", lambda x: (x == player_B_name).sum()),
            tb_status=("Tiebreak_status", "last"),
            games_A=("Games_player_A", "last"),
            games_B=("Games_player_B", "last"),
            sets_A=("Sets_player_A", "last"),
            sets_B=("Sets_player_B", "last"),
        )
        .reset_index()
    )

    games["dominance"] = 1 / (games["total_points"] - 3).clip(lower=1)
    games.loc[games["points_B"] > games["points_A"], "dominance"] *= -1

    x, labels, values, colors, set_ranges = [], [], [], [], []
    current_x = 0

    for set_no in sorted(games["set_number"].unique()):
        gset = games[games["set_number"] == set_no].copy()
        start_x = current_x
        for _, row in gset.iterrows():
            x.append(current_x)
            labels.append(str(int(row["game_number"])))
            values.append(row["dominance"])
            colors.append("forestgreen" if row["dominance"] > 0 else "crimson")
            current_x += 1
        end_x = current_x - 1
        final_row = gset.iloc[-1]
        set_ranges.append({
            "set": int(set_no),
            "start": start_x,
            "end": end_x,
            "games_A": int(final_row["games_A"]),
            "games_B": int(final_row["games_B"]),
            "tb_status": final_row["tb_status"],
            "tb_A": int(final_row["points_A"]) if final_row["tb_status"] in ["tiebreak", "super_tiebreak"] else None,
            "tb_B": int(final_row["points_B"]) if final_row["tb_status"] in ["tiebreak", "super_tiebreak"] else None,
        })
        current_x += 1

    fig, ax = plt.subplots(figsize=(max(12, len(x) * 0.85), 7), dpi=170)
    for i, s in enumerate(set_ranges):
        left = s["start"] - 0.5
        right = s["end"] + 0.5
        if i % 2 == 0:
            ax.axvspan(left, right, alpha=0.08)
        if s["tb_status"] == "super_tiebreak":
            text = f"Set {s['set']} ({s['tb_A']}-{s['tb_B']} STB)"
        elif s["tb_status"] == "tiebreak":
            text = f"Set {s['set']} ({s['games_A']}-{s['games_B']}, TB {s['tb_A']}-{s['tb_B']})"
        else:
            text = f"Set {s['set']} ({s['games_A']}-{s['games_B']})"
        ax.text(left + 0.1, 0.98, text, transform=ax.get_xaxis_transform(), ha="left", va="top", fontsize=11, fontweight="bold")

    ax.axhline(0, color="gray")
    ax.bar(x, values, color=colors)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.tick_params(axis="y", labelsize=10)
    ax.set_ylim(-1.1, 1.25)
    ax.set_xlim(-1, max(x) + 1 if x else 1)
    ax.set_xlabel("Game", fontsize=11)
    ax.set_ylabel("Game dominance", fontsize=11)
    ax.set_title("Tennis Game Dominance by Set", fontsize=17)
    fig.tight_layout()
    return fig



def plot_points_by_description(df_match, player_name):
    df = df_match.copy()
    df["description"] = df["description"].fillna("unknown")
    df = df[df["description"].str.lower() != "unknown"].copy()

    won_counts = df[df["pointscorer"] == player_name]["description"].value_counts()
    lost_counts = df[df["pointscorer"] != player_name]["description"].value_counts()

    all_descriptions = list(set(won_counts.index).union(set(lost_counts.index)))

    if not all_descriptions:
        fig, ax = plt.subplots(figsize=(12, 4), dpi=170)
        ax.text(0.5, 0.5, "No point descriptions recorded yet", ha="center", va="center", fontsize=13)
        ax.axis("off")
        fig.tight_layout()
        return fig

    plot_df = pd.DataFrame({
        "description": all_descriptions,
        "won": [int(won_counts.get(desc, 0)) for desc in all_descriptions],
        "lost": [int(lost_counts.get(desc, 0)) for desc in all_descriptions],
    })
    plot_df["sort_score"] = plot_df["won"] - plot_df["lost"]
    plot_df["total"] = plot_df["won"] + plot_df["lost"]
    plot_df = plot_df.sort_values(
        by=["sort_score", "won", "total", "description"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)

    labels = [desc.replace("_", " ").title() for desc in plot_df["description"]]
    won_values = plot_df["won"].to_numpy(dtype=float)
    lost_values = plot_df["lost"].to_numpy(dtype=float)
    x = np.arange(len(labels))
    width = 0.44

    fig_width = max(13, len(labels) * 1.15)
    fig, ax = plt.subplots(figsize=(fig_width, 6.8), dpi=170)
    bars_won = ax.bar(x - width / 2, won_values, width=width, color="#1696d2", edgecolor="black", linewidth=0.8, label="Won points")
    bars_lost = ax.bar(x + width / 2, lost_values, width=width, color="#ff1122", edgecolor="black", linewidth=0.8, label="Lost points")

    ymax = max(np.max(won_values) if len(won_values) else 0, np.max(lost_values) if len(lost_values) else 0, 1)
    label_offset = max(0.08, ymax * 0.025)

    for bars in [bars_won, bars_lost]:
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    height + label_offset,
                    f"{int(height)}",
                    ha="center",
                    va="bottom",
                    fontsize=10,
                )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=10)
    ax.set_ylabel("Frequency", fontsize=11, fontweight="bold")
    ax.set_xlabel("Description", fontsize=11, fontweight="bold")
    ax.set_title(f"{player_name}: Won and Lost Points by Description", fontsize=16, fontweight="bold")
    ax.set_ylim(0, ymax * 1.12 + label_offset)
    ax.margins(x=0.02)
    ax.legend(loc="upper left")
    fig.tight_layout()
    return fig

def reset_match_state():
    st.session_state.match_started = False
    st.session_state.finished = False
    st.session_state.rows = []
    st.session_state.current_server = None
    st.session_state.first_server = None
    st.session_state.set_no = 1
    st.session_state.game_no = 1
    st.session_state.point_no_in_game = 0
    st.session_state.sets_A = 0
    st.session_state.sets_B = 0
    st.session_state.games_A = 0
    st.session_state.games_B = 0
    st.session_state.points_A = 0
    st.session_state.points_B = 0
    st.session_state.tiebreak_status = ""
    st.session_state.tiebreak_first_server = None
    st.session_state.tiebreak_point_index = 0


def init_state():
    defaults = {
        "match_started": False,
        "finished": False,
        "rows": [],
        "current_server": None,
        "first_server": None,
        "set_no": 1,
        "game_no": 1,
        "point_no_in_game": 0,
        "sets_A": 0,
        "sets_B": 0,
        "games_A": 0,
        "games_B": 0,
        "points_A": 0,
        "points_B": 0,
        "tiebreak_status": "",
        "tiebreak_first_server": None,
        "tiebreak_point_index": 0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def add_point(scorer, description, serve_result):
    player_A = st.session_state.player_A
    player_B = st.session_state.player_B
    current_server = st.session_state.current_server
    tiebreak_status = st.session_state.tiebreak_status

    if tiebreak_status == "":
        server = current_server
    else:
        server = tiebreak_server_for_point(
            st.session_state.tiebreak_first_server,
            player_A,
            player_B,
            st.session_state.tiebreak_point_index,
        )

    serve_result_A = serve_result if server == player_A else ""
    serve_result_B = serve_result if server == player_B else ""
    st.session_state.point_no_in_game += 1

    st.session_state.rows.append({
        "description": description,
        "pointscorer": scorer,
        "server": server,
        "serve_result_player_A": serve_result_A,
        "serve_result_player_B": serve_result_B,
        "set_number": st.session_state.set_no,
        "game_number": st.session_state.game_no,
        "point_number_in_game": st.session_state.point_no_in_game,
        "Tiebreak_status": tiebreak_status,
    })

    if tiebreak_status == "":
        if scorer == player_A:
            st.session_state.points_A += 1
        else:
            st.session_state.points_B += 1

        game_winner = None
        if st.session_state.points_A >= 4 and st.session_state.points_A - st.session_state.points_B >= 2:
            game_winner = player_A
        elif st.session_state.points_B >= 4 and st.session_state.points_B - st.session_state.points_A >= 2:
            game_winner = player_B

        if game_winner is not None:
            if game_winner == player_A:
                st.session_state.games_A += 1
            else:
                st.session_state.games_B += 1

            st.session_state.points_A = 0
            st.session_state.points_B = 0
            st.session_state.point_no_in_game = 0

            set_winner = None
            if st.session_state.games_A >= 6 and st.session_state.games_A - st.session_state.games_B >= 2:
                set_winner = player_A
            elif st.session_state.games_B >= 6 and st.session_state.games_B - st.session_state.games_A >= 2:
                set_winner = player_B

            if set_winner is not None:
                if set_winner == player_A:
                    st.session_state.sets_A += 1
                else:
                    st.session_state.sets_B += 1

                if st.session_state.sets_A == 2 or st.session_state.sets_B == 2:
                    st.session_state.finished = True
                    return

                st.session_state.set_no += 1
                st.session_state.game_no = 1
                st.session_state.games_A = 0
                st.session_state.games_B = 0
            else:
                if st.session_state.games_A == 6 and st.session_state.games_B == 6:
                    if st.session_state.match_type == "doubles" and st.session_state.set_no == 3:
                        st.session_state.tiebreak_status = "super_tiebreak"
                    else:
                        st.session_state.tiebreak_status = "tiebreak"
                    st.session_state.tiebreak_first_server = other_player(current_server, player_A, player_B)
                    st.session_state.tiebreak_point_index = 0
                    st.session_state.point_no_in_game = 0
                    st.session_state.game_no = 13 if st.session_state.tiebreak_status == "tiebreak" else 1
                else:
                    st.session_state.current_server = other_player(current_server, player_A, player_B)
                    st.session_state.game_no += 1
    else:
        if scorer == player_A:
            st.session_state.points_A += 1
        else:
            st.session_state.points_B += 1

        st.session_state.tiebreak_point_index += 1
        target = 10 if st.session_state.tiebreak_status == "super_tiebreak" else 7
        tb_winner = None
        if st.session_state.points_A >= target and st.session_state.points_A - st.session_state.points_B >= 2:
            tb_winner = player_A
        elif st.session_state.points_B >= target and st.session_state.points_B - st.session_state.points_A >= 2:
            tb_winner = player_B

        if tb_winner is not None:
            if tb_winner == player_A:
                st.session_state.sets_A += 1
            else:
                st.session_state.sets_B += 1

            st.session_state.current_server = other_player(st.session_state.tiebreak_first_server, player_A, player_B)
            st.session_state.points_A = 0
            st.session_state.points_B = 0
            st.session_state.point_no_in_game = 0
            st.session_state.tiebreak_status = ""
            st.session_state.tiebreak_first_server = None
            st.session_state.tiebreak_point_index = 0

            if st.session_state.sets_A == 2 or st.session_state.sets_B == 2:
                st.session_state.finished = True
                return

            st.session_state.set_no += 1
            st.session_state.game_no = 1
            st.session_state.games_A = 0
            st.session_state.games_B = 0


def rebuild_state_from_rows(saved_rows, player_A, player_B, first_server, match_type):
    reset_match_state()
    st.session_state.player_A = player_A
    st.session_state.player_B = player_B
    st.session_state.current_server = first_server
    st.session_state.first_server = first_server
    st.session_state.match_type = match_type
    st.session_state.match_started = True
    for row in saved_rows:
        sr = row["serve_result_player_A"] if row["serve_result_player_A"] else row["serve_result_player_B"]
        add_point(row["pointscorer"], row["description"], sr)


def main():
    st.set_page_config(page_title="Tennis Match Stats", layout="wide")
    init_state()

    st.title("Tennis Match Tracker")
    st.caption("Track points live on your phone and see match stats instantly.")

    with st.sidebar:
        st.header("Match setup")
        player_A = st.text_input("Player A", value=st.session_state.get("player_A", "Player A"))
        player_B = st.text_input("Player B", value=st.session_state.get("player_B", "Player B"))
        first_server = st.selectbox("First server", [player_A, player_B], index=0)
        match_type = st.selectbox("Match type", ["singles", "doubles"], index=0)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Start / Reset"):
                reset_match_state()
                st.session_state.player_A = player_A
                st.session_state.player_B = player_B
                st.session_state.current_server = first_server
                st.session_state.first_server = first_server
                st.session_state.match_type = match_type
                st.session_state.match_started = True
                st.rerun()
        with col2:
            if st.button("Undo last") and st.session_state.rows:
                saved_rows = st.session_state.rows[:-1]
                player_A_saved = st.session_state.get("player_A", player_A)
                player_B_saved = st.session_state.get("player_B", player_B)
                first_server_saved = st.session_state.get("first_server") or first_server
                match_type_saved = st.session_state.get("match_type", match_type)
                rebuild_state_from_rows(saved_rows, player_A_saved, player_B_saved, first_server_saved, match_type_saved)
                st.rerun()

    if not st.session_state.match_started:
        st.info("Enter the player names in the sidebar, choose the first server, then tap Start / Reset.")
        return

    player_A = st.session_state.player_A
    player_B = st.session_state.player_B
    server_now = current_server_name()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Sets", f"{player_A} {st.session_state.sets_A} - {st.session_state.sets_B} {player_B}")
    with col2:
        st.metric("Games", f"{player_A} {st.session_state.games_A} - {st.session_state.games_B} {player_B}")
    with col3:
        if st.session_state.tiebreak_status:
            st.metric("Tiebreak", f"{player_A} {st.session_state.points_A} - {st.session_state.points_B} {player_B}")
        else:
            scoreA, scoreB = tennis_score(st.session_state.points_A, st.session_state.points_B)
            st.metric("Current game", f"{player_A} {scoreA} - {scoreB} {player_B}")

    if st.session_state.tiebreak_status:
        st.write(f"**Server:** {server_now}  ")
        st.write(f"**Mode:** {st.session_state.tiebreak_status}")
    else:
        st.write(f"**Server:** {server_now}")

    st.subheader("Add point")
    c1, c2, c3 = st.columns(3)

    scorer_options = [player_A, player_B]
    current_scorer = st.session_state.get("ui_scorer", scorer_options[0])
    st.session_state.ui_scorer = pick_valid(current_scorer, scorer_options)
    with c1:
        scorer = st.selectbox("Who won the point?", scorer_options, key="ui_scorer")

    valid_descriptions = valid_point_descriptions(server_now, scorer)
    current_description = st.session_state.get("ui_description", valid_descriptions[0])
    st.session_state.ui_description = pick_valid(current_description, valid_descriptions)
    with c2:
        description = st.selectbox("Point description", valid_descriptions, key="ui_description")

    valid_serves = valid_serve_results(server_now, scorer, description)
    current_serve = st.session_state.get("ui_serve_result", valid_serves[0])
    st.session_state.ui_serve_result = pick_valid(current_serve, valid_serves)
    with c3:
        serve_result = st.selectbox("Serve result", valid_serves, key="ui_serve_result")

    if st.button("Add point"):
        add_point(scorer, description, serve_result)
        st.rerun()

    if st.session_state.rows:
        df = pd.DataFrame(st.session_state.rows)
        df_match = build_match_dataframe(df, player_A, player_B, st.session_state.match_type)
        stats_df = generate_match_stats(df_match, player_A, player_B)

        st.subheader("Live stats")
        st.dataframe(stats_df, use_container_width=True)

        st.subheader("Charts")
        st.caption("The graphs are now full-width and high-resolution so they are much easier to read on a phone.")

        fig_summary = plot_stats_rotated(stats_df)
        st.pyplot(fig_summary, use_container_width=True)
        render_figure_download(fig_summary, "match_summary")
        plt.close(fig_summary)

        fig_dominance = plot_dominance(df_match, player_A, player_B)
        st.pyplot(fig_dominance, use_container_width=True)
        render_figure_download(fig_dominance, "game_dominance")
        plt.close(fig_dominance)

        st.subheader("Points won and lost by description")
        st.caption("These charts show which point descriptions each player won with most often, and which descriptions they lost points on most often.")

        fig_desc_A = plot_points_by_description(df_match, player_A)
        st.pyplot(fig_desc_A, use_container_width=True)
        render_figure_download(fig_desc_A, f"{player_A.lower().replace(' ', '_')}_description_breakdown")
        plt.close(fig_desc_A)

        fig_desc_B = plot_points_by_description(df_match, player_B)
        st.pyplot(fig_desc_B, use_container_width=True)
        render_figure_download(fig_desc_B, f"{player_B.lower().replace(' ', '_')}_description_breakdown")
        plt.close(fig_desc_B)

        with st.expander("Show chart data tables"):
            st.write("**Match summary values**")
            st.dataframe(stats_df, use_container_width=True)

            dominance_table = (
                df_match.groupby(["set_number", "game_number"])
                .agg(
                    server=("server", "last"),
                    points_won_by_A=("pointscorer", lambda x: (x == player_A).sum()),
                    points_won_by_B=("pointscorer", lambda x: (x == player_B).sum()),
                    tiebreak_status=("Tiebreak_status", "last"),
                )
                .reset_index()
            )
            st.write("**Game dominance source data**")
            st.dataframe(dominance_table, use_container_width=True)

            description_df = df_match.copy()
            description_df["description"] = description_df["description"].fillna("unknown")
            description_df = description_df[description_df["description"].str.lower() != "unknown"].copy()

            description_table = pd.DataFrame({
                "Description": sorted(set(description_df["description"]))
            })
            description_table[f"{player_A} won"] = description_table["Description"].map(
                description_df[description_df["pointscorer"] == player_A]["description"].value_counts()
            ).fillna(0).astype(int)
            description_table[f"{player_A} lost"] = description_table["Description"].map(
                description_df[description_df["pointscorer"] != player_A]["description"].value_counts()
            ).fillna(0).astype(int)
            description_table[f"{player_B} won"] = description_table["Description"].map(
                description_df[description_df["pointscorer"] == player_B]["description"].value_counts()
            ).fillna(0).astype(int)
            description_table[f"{player_B} lost"] = description_table["Description"].map(
                description_df[description_df["pointscorer"] != player_B]["description"].value_counts()
            ).fillna(0).astype(int)

            st.write("**Point description source data**")
            if len(description_table):
                st.dataframe(description_table, use_container_width=True)
            else:
                st.info("No non-unknown point descriptions recorded yet.")

        st.subheader("Recorded points")
        st.dataframe(df_match, use_container_width=True)

        csv_bytes = df_match.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", data=csv_bytes, file_name="tennis_match.csv", mime="text/csv")

        if st.session_state.finished:
            st.success("Match finished.")


if __name__ == "__main__":
    main()
