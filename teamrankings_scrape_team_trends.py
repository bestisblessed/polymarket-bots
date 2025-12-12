import sys
from io import StringIO

import pandas as pd
import requests

TEAM_TO_ID = {
    "Arizona": "ARI",
    "Atlanta": "ATL",
    "Baltimore": "BAL",
    "Buffalo": "BUF",
    "Carolina": "CAR",
    "Chicago": "CHI",
    "Cincinnati": "CIN",
    "Cleveland": "CLE",
    "Dallas": "DAL",
    "Denver": "DEN",
    "Detroit": "DET",
    "Green Bay": "GB",
    "Houston": "HOU",
    "Indianapolis": "IND",
    "Jacksonville": "JAX",
    "Kansas City": "KC",
    "LA Chargers": "LAC",
    "LA Rams": "LAR",
    "Las Vegas": "LV",
    "Miami": "MIA",
    "Minnesota": "MIN",
    "New England": "NE",
    "New Orleans": "NO",
    "NY Giants": "NYG",
    "NY Jets": "NYJ",
    "Philadelphia": "PHI",
    "Pittsburgh": "PIT",
    "San Francisco": "SF",
    "Seattle": "SEA",
    "Tampa Bay": "TB",
    "Tennessee": "TEN",
    "Washington": "WAS",
}


def _table(url: str) -> pd.DataFrame:
    return pd.read_html(StringIO(requests.get(url, timeout=60).text))[0]


def _season_col(df: pd.DataFrame, season: int) -> str:
    s = str(season)
    for c in df.columns:
        if str(c).strip() == s:
            return c
    raise ValueError(f"Season column {season} not found in {list(df.columns)}")


def _series(url: str, season: int) -> pd.Series:
    df = _table(url)
    c = _season_col(df, season)
    return df.set_index("Team")[c].astype(float)


def main() -> None:
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2025

    pass_for = _series("https://www.teamrankings.com/nfl/stat/passing-yards-per-game", season)
    pass_against = _series("https://www.teamrankings.com/nfl/stat/opponent-passing-yards-per-game", season)
    rush_for = _series("https://www.teamrankings.com/nfl/stat/rushing-yards-per-game", season)
    rush_against = _series("https://www.teamrankings.com/nfl/stat/opponent-rushing-yards-per-game", season)

    df = (
        pd.DataFrame(
            {
                "Team": pass_for.index,
                "pass_yds_for": pass_for.values,
                "pass_yds_against": pass_against.reindex(pass_for.index).values,
                "rush_yds_for": rush_for.reindex(pass_for.index).values,
                "rush_yds_against": rush_against.reindex(pass_for.index).values,
            }
        )
        .assign(
            TeamID=lambda x: x["Team"].map(TEAM_TO_ID),
            Season=season,
            source_pass_for="https://www.teamrankings.com/nfl/stat/passing-yards-per-game",
            source_pass_against="https://www.teamrankings.com/nfl/stat/opponent-passing-yards-per-game",
            source_rush_for="https://www.teamrankings.com/nfl/stat/rushing-yards-per-game",
            source_rush_against="https://www.teamrankings.com/nfl/stat/opponent-rushing-yards-per-game",
        )
        .loc[:, ["Season", "TeamID", "Team", "pass_yds_for", "pass_yds_against", "rush_yds_for", "rush_yds_against", "source_pass_for", "source_pass_against", "source_rush_for", "source_rush_against"]]
        .sort_values("Team")
        .reset_index(drop=True)
    )

    df.to_csv(f"team_trends_teamrankings_{season}.csv", index=False)
    print(f"Wrote team_trends_teamrankings_{season}.csv ({len(df)} teams)")


if __name__ == "__main__":
    main()
