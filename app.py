
import streamlit as st
import pandas as pd
import re
import difflib

@st.cache_data
def load_data():
    return pd.read_csv("final_playoff_projection_model_with_positions.csv")

@st.cache_data
def load_dvp():
    return pd.read_csv("hybrid_positional_dvp_ranked_fixed.csv")

df = load_data()
dvp_ranked = load_dvp()

team_abbr = {
    "Atlanta Hawks": "ATL", "Orlando Magic": "ORL", "Memphis Grizzlies": "MEM", "Golden State Warriors": "GSW",
    "Boston Celtics": "BOS", "Brooklyn Nets": "BKN", "New York Knicks": "NYK", "Philadelphia 76ers": "PHI",
    "Toronto Raptors": "TOR", "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE", "Detroit Pistons": "DET",
    "Indiana Pacers": "IND", "Milwaukee Bucks": "MIL", "Charlotte Hornets": "CHA", "Miami Heat": "MIA",
    "Washington Wizards": "WAS", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Houston Rockets": "HOU",
    "LA Clippers": "LAC", "Los Angeles Lakers": "LAL", "Phoenix Suns": "PHX", "Sacramento Kings": "SAC",
    "San Antonio Spurs": "SAS", "New Orleans Pelicans": "NOP", "Minnesota Timberwolves": "MIN", "Oklahoma City Thunder": "OKC",
    "Portland Trail Blazers": "POR", "Utah Jazz": "UTA"
}
team_abbr_reverse = {v: k for k, v in team_abbr.items()}

position_map = {
    "G": ["PG", "SG"], "F": ["SF", "PF"], "C": ["C"], "F-C": ["PF", "C"], "C-F": ["C", "PF"],
    "G-F": ["SG", "SF"], "F-G": ["SF", "PF"], "PG": ["PG"], "SG": ["SG"], "SF": ["SF"], "PF": ["PF"]
}

slate_df = pd.DataFrame()
st.sidebar.title("📂 Upload Slate Batch")
slate_df = pd.DataFrame()
try:
    with open("slate.txt", "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
        games, i = [], 0
        while i < len(lines) - 10:
            try:
                t1, t2 = lines[i], lines[i+1]
                if t1 not in team_abbr or t2 not in team_abbr:
                    i += 1
                    continue
                spread1 = float(lines[i+2].replace("+", ""))
                spread2 = float(lines[i+7].replace("+", ""))
                total = None
                for j in range(i, i+14):
                    if 'O ' in lines[j] or 'U ' in lines[j]:
                        total = float(re.findall(r"\d+\.?\d*", lines[j])[0])
                        break
                games.append({
                    "Team1": team_abbr[t1], "Team2": team_abbr[t2],
                    "Spread1": spread1, "Spread2": spread2, "Total": total
                })
                i += 14
            except:
                i += 1
        slate_df = pd.DataFrame(games)
        st.sidebar.success("Slate loaded from slate.txt!")
        st.sidebar.dataframe(slate_df)
except FileNotFoundError:
    st.sidebar.warning("No slate.txt file found. Upload manually if needed.")

st.title("🔎 NBA Player Projection Lookup")
player_query = st.text_input("Search Player", placeholder="e.g. Trae Young")
stat_type = st.radio("Select Stat", ["Points", "Rebounds", "Assists", "PR", "PA", "RA", "PRA"], horizontal=True)

stat_column_map = {
    "Points": "PTS_adj", "Rebounds": "REB_adj", "Assists": "AST_adj",
    "PR": ["PTS_adj", "REB_adj"], "PA": ["PTS_adj", "AST_adj"],
    "RA": ["REB_adj", "AST_adj"], "PRA": ["PTS_adj", "REB_adj", "AST_adj"]
}
stat_to_dvp_suffix = {"Points": "PTS", "Rebounds": "REB", "Assists": "AST"}

if player_query:
    player_names = df["Player"].tolist()
    best_match = difflib.get_close_matches(player_query, player_names, n=1, cutoff=0.6)
    matches = df[df["Player"] == best_match[0]] if best_match else pd.DataFrame()
    if matches.empty:
        st.warning("No player found.")
    else:
        row = matches.iloc[0]
        team = row["Team"]
        pos = row["Position"]
        opp, opp_full, spread, total = None, None, 0, 224
        if not slate_df.empty:
            matchup = slate_df[(slate_df["Team1"] == team) | (slate_df["Team2"] == team)]
            if not matchup.empty:
                m = matchup.iloc[0]
                opp = m["Team2"] if m["Team1"] == team else m["Team1"]
                opp_full = team_abbr_reverse.get(opp, "")
                spread = m["Spread1"] if m["Team1"] == team else m["Spread2"]
                total = m["Total"]

        ts = row["TS%"]
        mpg = row["MPG"]
        pace_factor = total / 224
        blowout_penalty = 0.90 if abs(spread) >= 12 and mpg < 28 else 0.95 if abs(spread) >= 10 else 1.0

        pts, reb, ast = row["PTS_adj"], row["REB_adj"], row["AST_adj"]
        usage_proxy = pts / mpg if mpg > 0 else 0
        bonuses = {"PTS": 0, "REB": 0, "AST": 0}
        dvp_info = {}

        for stat in ["PTS", "REB", "AST"]:
            ranks = []
            for mapped_pos in position_map.get(pos, [pos]):
                col = f"{mapped_pos}_{stat}"
                if col in dvp_ranked.columns and opp_full in dvp_ranked["Team"].values:
                    rank = int(dvp_ranked.loc[dvp_ranked["Team"] == opp_full, col].values[0])
                    ranks.append(rank)
            if ranks:
                avg_rank = sum(ranks) / len(ranks)
                dvp_info[stat] = (f"avg_{stat}", round(avg_rank))
                # Tiered bonus logic
                if avg_rank <= 5:
                    bonuses[stat] = 0.06
                elif avg_rank <= 10:
                    bonuses[stat] = 0.03
                elif avg_rank <= 20:
                    bonuses[stat] = 0.0
                elif avg_rank <= 25:
                    bonuses[stat] = -0.03
                else:
                    bonuses[stat] = -0.06

        def apply(stat, base, is_pts):
            usage = 1.0
            if mpg >= 30:
                usage = 1.025  # 🔼 +2.5% boost for high-MPG playoff players
            elif mpg >= 20:
                usage = 0.985  # 🟨 -1.5% penalty for middle-MPG players (20–29 MPG)
            else:
                usage = 0.93   # 🔽 -7% penalty for low-MPG players (<20 MPG)

            val = base * (1 + bonuses[stat])
            if is_pts:
                val *= min(ts / 0.57, 1.07)

            return val * pace_factor * blowout_penalty * usage

        projections = {
            "Points": apply("PTS", pts, True),
            "Rebounds": apply("REB", reb, False),
            "Assists": apply("AST", ast, False)
        }
        projections["PR"] = projections["Points"] + projections["Rebounds"]
        projections["PA"] = projections["Points"] + projections["Assists"]
        projections["RA"] = projections["Rebounds"] + projections["Assists"]
        projections["PRA"] = projections["Points"] + projections["Rebounds"] + projections["Assists"]

        st.metric(label=f"{stat_type} Projection", value=round(projections[stat_type], 2))
        st.caption(f"{row['Player']} ({team} - {pos})")
        if opp:
            st.caption(f"🆚 Opponent: {opp} | Spread: {spread} | Total: {total}")

        st.markdown("### 🧠 Why this projection?")
        if stat_type in ["Points", "Rebounds", "Assists"]:
            key = {"Points": "PTS", "Rebounds": "REB", "Assists": "AST"}[stat_type]
            base = pts if key == "PTS" else reb if key == "REB" else ast
            ts_mult = min(ts / 0.57, 1.07) if key == "PTS" else 1.0
            dvp_bonus = bonuses[key]
            pace = pace_factor
            blowout = 0.95 if abs(spread) >= 10 else 1.0
            final = round(projections[stat_type], 2)
            explanation = f"Base: {round(base,2)} → TS: x{round(ts_mult,2)} → DvP: +{round(dvp_bonus*100,1)}% → Pace: x{round(pace,2)}"
            if blowout < 1.0:
                explanation += " → -5% Blowout"
            explanation += f" → **{final} final**"
            st.write(explanation)
            st.caption(f"⚡ Usage Proxy (PTS/MPG): {round(usage_proxy, 2)}")
            if key in dvp_info:
                col, rank = dvp_info[key]
                st.caption(f"📊 DvP Rank vs {col}: {rank} of 30")
        else:
            for sub in stat_type:
                st.write(f"{sub}: {round(projections[sub], 2)}")