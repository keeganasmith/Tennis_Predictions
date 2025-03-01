#!/usr/bin/env python3
"""
Data processing pipeline for tennis match data.
This script:
  - Loads raw match and player data.
  - Computes features such as serving percentages and break point statistics.
  - Generates rolling statistics (base and adjusted) by player.
  - Merges rolling stats back into the main DataFrame.
  - Performs final cleanup (dropping unwanted columns, handling NAs, etc.)
  - Saves the preprocessed DataFrame for later modeling.
"""

import joblib
import pandas as pd
import numpy as np
from datetime import datetime
import json
import warnings
from typing import List, Dict, Tuple, Any
import itertools

warnings.simplefilter(action='ignore', category=Warning)

# ======================================================
# Constants for column names
# ======================================================
PLAYER1_SERVE_WON = "PlayerTeam1.Sets[0].Stats.PointStats.TotalServicePointsWon.Dividend"
PLAYER1_SERVE_TOTAL = "PlayerTeam1.Sets[0].Stats.PointStats.TotalServicePointsWon.Divisor"

PLAYER2_SERVE_WON = "PlayerTeam2.Sets[0].Stats.PointStats.TotalServicePointsWon.Dividend"
PLAYER2_SERVE_TOTAL = "PlayerTeam2.Sets[0].Stats.PointStats.TotalServicePointsWon.Divisor"

PLAYER1_BP_WON = "PlayerTeam1.Sets[0].Stats.ServiceStats.BreakPointsSaved.Dividend"
PLAYER1_BP_TOTAL = "PlayerTeam1.Sets[0].Stats.PointStats.TotalPointsWon.Divisor"

PLAYER2_BP_WON = "PlayerTeam2.Sets[0].Stats.ServiceStats.BreakPointsSaved.Dividend"
PLAYER2_BP_TOTAL = "PlayerTeam2.Sets[0].Stats.PointStats.TotalPointsWon.Divisor"

PLAYER1_BP_CONVERTED = "PlayerTeam1.Sets[0].Stats.ReturnStats.BreakPointsConverted.Dividend"
PLAYER1_BP_CONVERTED_TOTAL = "PlayerTeam1.Sets[0].Stats.ReturnStats.BreakPointsConverted.Divisor"

PLAYER2_BP_CONVERTED = "PlayerTeam2.Sets[0].Stats.ReturnStats.BreakPointsConverted.Dividend"
PLAYER2_BP_CONVERTED_TOTAL = "PlayerTeam2.Sets[0].Stats.ReturnStats.BreakPointsConverted.Divisor"

PLAYER1_RETURN = "PlayerTeam1.Sets[0].Stats.PointStats.TotalReturnPointsWon.Dividend"
PLAYER1_RETURN_TOTAL = "PlayerTeam2.Sets[0].Stats.PointStats.TotalReturnPointsWon.Divisor"

PLAYER2_RETURN = "PlayerTeam2.Sets[0].Stats.PointStats.TotalReturnPointsWon.Dividend"
PLAYER2_RETURN_TOTAL = "PlayerTeam2.Sets[0].Stats.PointStats.TotalReturnPointsWon.Divisor"

PLAYER1_ACES = "PlayerTeam1.Sets[0].Stats.ServiceStats.Aces.Number"
PLAYER2_ACES = "PlayerTeam2.Sets[0].Stats.ServiceStats.Aces.Number"

PLAYER1_DOUBLE = "PlayerTeam1.Sets[0].Stats.ServiceStats.DoubleFaults.Number"
PLAYER2_DOUBLE = "PlayerTeam2.Sets[0].Stats.ServiceStats.DoubleFaults.Number"

PLAYER1_COUNTRY_CODE = "PlayerTeam1.PlayerCountryCode"
PLAYER2_COUNTRY_CODE = "PlayerTeam2.PlayerCountryCode"
country_mapping = {
    'GER': 'Germany', 'MAR': 'Morocco', 'NED': 'Netherlands', 'SUI': 'Switzerland', 'SWE': 'Sweden',
    'BLR': 'Belarus', 'ITA': 'Italy', 'ARG': 'Argentina', 'CZE': 'Czech Republic', 'ESP': 'Spain',
    'CRC': 'Costa Rica', 'RUS': 'Russia', 'USA': 'United States', 'FRA': 'France', 'QAT': 'Qatar',
    'CRO': 'Croatia', 'GBR': 'United Kingdom', 'FIN': 'Finland', 'IND': 'India', 'HAI': 'Haiti',
    'BUL': 'Bulgaria', 'ISR': 'Israel', 'AUT': 'Austria', 'ZIM': 'Zimbabwe', 'BEL': 'Belgium',
    'SVK': 'Slovakia', 'UZB': 'Uzbekistan', 'ROU': 'Romania', 'AUS': 'Australia', 'JPN': 'Japan',
    'MON': 'Monaco', 'SRB': 'Serbia', 'BRA': 'Brazil', 'ARM': 'Armenia', 'NZL': 'New Zealand',
    'ECU': 'Ecuador', 'UKR': 'Ukraine', 'RSA': 'South Africa', 'THA': 'Thailand', 'PHI': 'Philippines',
    'CAN': 'Canada', 'CHI': 'Chile', 'BAH': 'Bahamas', 'MEX': 'Mexico', 'DEN': 'Denmark',
    'VEN': 'Venezuela', 'COL': 'Colombia', 'NOR': 'Norway', 'PAR': 'Paraguay', 'HUN': 'Hungary',
    'URU': 'Uruguay', 'KOR': 'South Korea', 'HKG': 'Hong Kong', 'CHN': 'China', 'PER': 'Peru',
    'TPE': 'Taiwan', 'CYP': 'Cyprus', 'LUX': 'Luxembourg', 'KAZ': 'Kazakhstan', 'UAE': 'United Arab Emirates',
    'GEO': 'Georgia', 'SLO': 'Slovenia', 'POL': 'Poland', 'GRE': 'Greece', 'AZE': 'Azerbaijan',
    'ALG': 'Algeria', 'JAM': 'Jamaica', 'BIH': 'Bosnia and Herzegovina', 'KUW': 'Kuwait', 'PAK': 'Pakistan',
    'VIE': 'Vietnam', 'LAT': 'Latvia', 'MDA': 'Moldova', 'AND': 'Andorra', 'LBN': 'Lebanon',
    'POR': 'Portugal', 'LTU': 'Lithuania', 'IRL': 'Ireland', 'AHO': 'Netherlands Antilles', 'SLE': 'Sierra Leone',
    'MKD': 'North Macedonia', 'SRI': 'Sri Lanka', 'SYR': 'Syria', 'OMA': 'Oman', 'TOG': 'Togo',
    'TUR': 'Turkey', 'ESA': 'El Salvador', 'DOM': 'Dominican Republic', 'EST': 'Estonia', 'CIV': 'Ivory Coast',
    'MAS': 'Malaysia', 'EGY': 'Egypt', 'TUN': 'Tunisia', 'BAR': 'Barbados', 'INA': 'Indonesia',
    'GUA': 'Guatemala', 'KOS': 'Kosovo', 'BOL': 'Bolivia', 'TKM': 'Turkmenistan', 'SGP': 'Singapore',
    'JOR': 'Jordan', 'NMI': 'Northern Mariana Islands'
}
# ======================================================
# Helper Classes and Functions
# ======================================================
class PlayerRank:
    """
    Encapsulates player ranking information.
    Example rank dict:
      {'RankDate': '1995-01-09T00:00:00', 'SglRollRank': 2, ...}
    """
    def __init__(self, obj: Dict[str, Any]):
        self.RankDate = obj["RankDate"]
        self.SglRollRank = obj["SglRollRank"]
        self.SglRollTie = obj["SglRollTie"]
        self.SglRollPoints = obj["SglRollPoints"]
        self.SglRaceRank = obj["SglRaceRank"]
        self.SglRaceTie = obj["SglRaceTie"]
        self.SglRacePoints = obj["SglRacePoints"]
        self.DblRollRank = obj["DblRollRank"]
        self.DblRollTie = obj["DblRollTie"]
        self.DblRollPoints = obj["DblRollPoints"]
    
    def __str__(self) -> str:
        return json.dumps(self.__dict__, indent=4)


def replace_divide_by_zero(df: pd.DataFrame, divisor_col: str, resulting_col: str) -> pd.DataFrame:
    """Replace entries in resulting_col with 0 when divisor_col equals 0."""
    print(f"Dividend median for {resulting_col}: {df[resulting_col].median()}")
    df.loc[df[divisor_col] == 0, resulting_col] = 0
    return df


def fill_na_columns(df: pd.DataFrame, columns: List[str], value: Any) -> pd.DataFrame:
    """Fill NA values for the given columns with the specified value."""
    return df.fillna({col: value for col in columns})


def get_new_column_names(columns: List[str], prefix: str) -> List[str]:
    """Prepend a prefix to each column name in the list."""
    return [f"{prefix}.{col}" for col in columns]


def get_rename_mapping(original_columns: List[str], prefix: str) -> Dict[str, str]:
    """Map each original column to a new name with the given prefix."""
    return {col: f"{prefix}.{col}" for col in original_columns}


def compute_rolling(group: pd.DataFrame, col: str, window_days: int, func: str, shift: int = 1) -> pd.Series:
    """
    Compute a shifted, time-based rolling statistic.
    
    Parameters:
      group: DataFrame with a DatetimeIndex.
      col: The column to aggregate.
      window_days: The window in days.
      func: Aggregation function (e.g., 'sum', 'count').
      shift: Number of periods to shift (default excludes current row).
    """
    return group[col].shift(shift).rolling(f"{window_days}D").agg(func).fillna(0)


# ======================================================
# Feature Engineering Functions
# ======================================================
def generate_adjusted_rolling_columns(df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """
    Create new adjusted columns for each team and column.
    For each team, multiply the original column by the opponent factor.
    """
    for team in ["PlayerTeam1", "PlayerTeam2"]:
        for col in columns:
            new_col = f"{team}.{col}.adjusted"
            df[new_col] = df[f"{team}.{col}"] * df[f"{team}.opponent_factor"]
    return df


def retrieve_player_stats(
    df: pd.DataFrame,
    num_years: int,
    date_column: str = "StartDate",
    include_adjusted: bool = True,
    rolling_specs: List[Dict[str, str]] = None,
    rolling_avg_specs: List[Dict[str, str]] = None
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Convert wide-format match DataFrame into a long-format player stats DataFrame.
    Compute rolling statistics (base and, if desired, adjusted) over a window of num_years.
    """
    if rolling_specs is None:
        rolling_specs = [
            {"new_col": "rolling_match_count", "source_col": "is_winner", "func": "count"},
            {"new_col": "rolling_serve_pct_sum", "source_col": "serve_pct", "func": "sum"},
            {"new_col": "rolling_bp_pct_sum", "source_col": "bp_saved_pct", "func": "sum"},
            {"new_col": "rolling_bp_conv_pct_sum", "source_col": "bp_conv_pct", "func": "sum"},
            {"new_col": "rolling_return_pct_sum", "source_col": "return_pct", "func": "sum"},
            {"new_col": "matches_won", "source_col": "is_winner", "func": "sum"},
            {"new_col": "rolling_aces_pct_sum", "source_col": "aces_pct", "func": "sum"},
            {"new_col": "rolling_double_pct_sum", "source_col": "double_pct", "func": "sum"},
            {"new_col": "rolling_sgl_roll_rank", "source_col": "sgl_roll_rank", "func": "sum"}
        ]
    if rolling_avg_specs is None:
        rolling_avg_specs = [
            {"new_col": "rolling_avg_serve_pct", "sum_col": "rolling_serve_pct_sum"},
            {"new_col": "rolling_avg_bp_pct", "sum_col": "rolling_bp_pct_sum"},
            {"new_col": "rolling_avg_bp_conv_pct", "sum_col": "rolling_bp_conv_pct_sum"},
            {"new_col": "rolling_avg_return_pct", "sum_col": "rolling_return_pct_sum"},
            {"new_col": "rolling_avg_aces_pct", "sum_col": "rolling_aces_pct_sum"},
            {"new_col": "rolling_avg_double_pct", "sum_col": "rolling_double_pct_sum"},
            {"new_col": "rolling_avg_sgl_roll", "sum_col": "rolling_sgl_roll_rank"}
        ]
    
    adjusted_rolling_specs = [
        {"new_col": "rolling_serve_pct_adjusted_sum", "source_col": "serve_pct_adjusted", "func": "sum"},
        {"new_col": "rolling_bp_saved_pct_adjusted_sum", "source_col": "bp_saved_pct_adjusted", "func": "sum"},
        {"new_col": "rolling_bp_conv_pct_adjusted_sum", "source_col": "bp_conv_pct_adjusted", "func": "sum"},
        {"new_col": "rolling_return_pct_adjusted_sum", "source_col": "return_pct_adjusted", "func": "sum"},
    ]
    adjusted_rolling_avg_specs = [
        {"new_col": "rolling_avg_serve_pct_adjusted", "sum_col": "rolling_serve_pct_adjusted_sum"},
        {"new_col": "rolling_avg_bp_saved_pct_adjusted", "sum_col": "rolling_bp_saved_pct_adjusted_sum"},
        {"new_col": "rolling_avg_bp_conv_pct_adjusted", "sum_col": "rolling_bp_conv_pct_adjusted_sum"},
        {"new_col": "rolling_avg_return_pct_adjusted", "sum_col": "rolling_return_pct_adjusted_sum"},
    ]
    
    df[date_column] = pd.to_datetime(df[date_column], errors="coerce")
    df = df.dropna(subset=[date_column]).sort_values(date_column).reset_index(drop=True)
    
    long_data = {
        "player_id": df["PlayerTeam1.PlayerId"].tolist() + df["PlayerTeam2.PlayerId"].tolist(),
        "match_id": df["match_id"].tolist() + df["match_id"].tolist(),
        date_column: df[date_column].tolist() + df[date_column].tolist(),
        "serve_pct": df["PlayerTeam1.serve_pct1"].tolist() + df["PlayerTeam2.serve_pct1"].tolist(),
        "bp_saved_pct": df["PlayerTeam1.bp_save_pct1"].tolist() + df["PlayerTeam2.bp_save_pct1"].tolist(),
        "bp_conv_pct": df["PlayerTeam1.bp_conv_pct1"].tolist() + df["PlayerTeam2.bp_conv_pct1"].tolist(),
        "return_pct": df["PlayerTeam1.return_pct1"].tolist() + df["PlayerTeam2.return_pct1"].tolist(),
        "aces_pct": df["PlayerTeam1.aces_pct1"].tolist() + df["PlayerTeam2.aces_pct1"].tolist(),
        "double_pct": df["PlayerTeam1.double_pct1"].tolist() + df["PlayerTeam2.double_pct1"].tolist(),
        "opponent_factor": df["PlayerTeam1.opponent_factor"].tolist() + df["PlayerTeam2.opponent_factor"].tolist(),
        "sgl_roll_rank": df["PlayerTeam1.SglRollRank"].tolist() + df["PlayerTeam2.SglRollRank"].tolist(),
        "is_winner": [1] * len(df) + [0] * len(df)
    }
    if include_adjusted:
        long_data["serve_pct_adjusted"] = (
            df["PlayerTeam1.serve_pct1.adjusted"].tolist() +
            df["PlayerTeam2.serve_pct1.adjusted"].tolist()
        )
        long_data["bp_saved_pct_adjusted"] = (
            df["PlayerTeam1.bp_save_pct1.adjusted"].tolist() +
            df["PlayerTeam2.bp_save_pct1.adjusted"].tolist()
        )
        long_data["bp_conv_pct_adjusted"] = (
            df["PlayerTeam1.bp_conv_pct1.adjusted"].tolist() +
            df["PlayerTeam2.bp_conv_pct1.adjusted"].tolist()
        )
        long_data["return_pct_adjusted"] = (
            df["PlayerTeam1.return_pct1.adjusted"].tolist() +
            df["PlayerTeam2.return_pct1.adjusted"].tolist()
        )
    player_stats = pd.DataFrame(long_data)
    player_stats[date_column] = pd.to_datetime(player_stats[date_column], errors="coerce")
    player_stats = player_stats.dropna(subset=[date_column])
    print("Sorting player stats by player_id and date...")
    player_stats.sort_values(["player_id", date_column], inplace=True)
    
    print("Performing rolling calculations...")
    window_days = num_years * 365 

    def rolling_stats(group: pd.DataFrame) -> pd.DataFrame:
        group = group.set_index(date_column)
        for spec in rolling_specs:
            group[spec["new_col"]] = compute_rolling(group, spec["source_col"], window_days, spec["func"], shift=1)
        for spec in rolling_avg_specs:
            group[spec["new_col"]] = (group[spec["sum_col"]] / group["rolling_match_count"]).fillna(0)
        if include_adjusted:
            for spec in adjusted_rolling_specs:
                group[spec["new_col"]] = compute_rolling(group, spec["source_col"], window_days, spec["func"], shift=1)
            for spec in adjusted_rolling_avg_specs:
                group[spec["new_col"]] = (group[spec["sum_col"]] / group["rolling_match_count"]).fillna(0)
        return group.reset_index()
    
    player_stats = player_stats.groupby("player_id", group_keys=False).apply(rolling_stats)
    
    base_new_stats = [spec["new_col"] for spec in rolling_avg_specs] + ["rolling_match_count", "matches_won"]
    new_stat_columns = base_new_stats.copy()
    if include_adjusted:
        new_stat_columns += [spec["new_col"] for spec in adjusted_rolling_avg_specs]
    
    return player_stats, new_stat_columns


def merge_dataframes(
    df: pd.DataFrame,
    other_df: pd.DataFrame,
    merge_columns: List[str],
    rename_mapping: Dict[str, str],
    is_winner: int
) -> pd.DataFrame:
    """
    Merge rolling statistics (filtered by is_winner) into the main DataFrame.
    """
    merged = df.merge(
        other_df[other_df["is_winner"] == is_winner][merge_columns],
        on="match_id",
        how="left",
        suffixes=("", "_winner")
    ).rename(columns=rename_mapping)
    return merged


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate per-match features (serving %, break point stats, etc.) and create opponent factor.
    Also, generate adjusted rolling columns.
    """
    df["PlayerTeam1.serve_pct1"] = df[PLAYER1_SERVE_WON] / df[PLAYER1_SERVE_TOTAL]
    df["PlayerTeam2.serve_pct1"] = df[PLAYER2_SERVE_WON] / df[PLAYER2_SERVE_TOTAL]
    df["PlayerTeam1.bp_save_pct1"] = df[PLAYER1_BP_WON] / df[PLAYER1_BP_TOTAL]
    df["PlayerTeam2.bp_save_pct1"] = df[PLAYER2_BP_WON] / df[PLAYER2_BP_TOTAL]
    df["PlayerTeam1.bp_conv_pct1"] = df[PLAYER1_BP_CONVERTED] / df[PLAYER1_BP_CONVERTED_TOTAL]
    df["PlayerTeam2.bp_conv_pct1"] = df[PLAYER2_BP_CONVERTED] / df[PLAYER2_BP_CONVERTED_TOTAL]
    df["PlayerTeam1.return_pct1"] = df[PLAYER1_RETURN] / df[PLAYER1_RETURN_TOTAL]
    df["PlayerTeam2.return_pct1"] = df[PLAYER2_RETURN] / df[PLAYER2_RETURN_TOTAL]
    df["PlayerTeam1.aces_pct1"] = df[PLAYER1_ACES] / df[PLAYER1_SERVE_TOTAL]
    df["PlayerTeam2.aces_pct1"] = df[PLAYER2_ACES] / df[PLAYER2_SERVE_TOTAL]
    df["PlayerTeam1.double_pct1"] = df[PLAYER1_DOUBLE] / df[PLAYER1_SERVE_TOTAL]
    df["PlayerTeam2.double_pct1"] = df[PLAYER2_DOUBLE] / df[PLAYER2_SERVE_TOTAL]
    df["PlayerTeam1.years_pro"] = df["EventYear"] - df["PlayerTeam1.ProYear"]
    df["PlayerTeam2.years_pro"] = df["EventYear"] - df["PlayerTeam2.ProYear"]
    df["PlayerTeam1.Age"] = df["EventYear"] - (2025 - df["PlayerTeam1.Age"])
    df["PlayerTeam2.Age"] = df["EventYear"] - (2025 - df["PlayerTeam2.Age"])
    df["PlayerTeam1.AgeDifference"] = df["PlayerTeam2.Age"] - df["PlayerTeam1.Age"]
    df["PlayerTeam2.AgeDifference"] = df["PlayerTeam1.Age"] - df["PlayerTeam2.Age"]
    
    df = replace_divide_by_zero(df, PLAYER1_BP_TOTAL, "PlayerTeam1.bp_save_pct1")
    df = replace_divide_by_zero(df, PLAYER2_BP_TOTAL, "PlayerTeam2.bp_save_pct1")
    df = replace_divide_by_zero(df, PLAYER1_BP_CONVERTED, "PlayerTeam1.bp_conv_pct1")
    df = replace_divide_by_zero(df, PLAYER2_BP_CONVERTED, "PlayerTeam2.bp_conv_pct1")
    df = replace_divide_by_zero(df, PLAYER1_RETURN, "PlayerTeam1.return_pct1")
    df = replace_divide_by_zero(df, PLAYER2_RETURN, "PlayerTeam2.return_pct1")
    
    # Create opponent factor as reciprocal of the opponent's ranking statistic.
    df["PlayerTeam1.opponent_factor"] = 1 / df["PlayerTeam2.SglRollRank"]
    df["PlayerTeam2.opponent_factor"] = 1 / df["PlayerTeam1.SglRollRank"]
    df = replace_divide_by_zero(df, "PlayerTeam2.SglRaceRank", "PlayerTeam1.opponent_factor")
    df = replace_divide_by_zero(df, "PlayerTeam1.SglRaceRank", "PlayerTeam2.opponent_factor")
    
    # Generate adjusted rolling columns (for serve_pct1, bp_save_pct1, etc.)
    rolling_cols = ["serve_pct1", "bp_save_pct1", "bp_conv_pct1", "return_pct1"]
    df = generate_adjusted_rolling_columns(df, rolling_cols)
    
    # Create a unique match identifier
    df["match_id"] = (df["MatchId"].astype(str) + "-" +
                      df["EventId"].astype(str) + "-" +
                      df["EventYear"].astype(str))
    
    # Compute rolling statistics for the overall dataset (window of 3 years)
    player_stats, new_stats_columns = retrieve_player_stats(df, 3)
    merge_cols = new_stats_columns + ["match_id"]
    winner_mapping = get_rename_mapping(new_stats_columns, "PlayerTeam1")
    loser_mapping = get_rename_mapping(new_stats_columns, "PlayerTeam2")
    
    print("Merging rolling averages...")
    df = merge_dataframes(df, player_stats, merge_cols, winner_mapping, is_winner=1)
    df = merge_dataframes(df, player_stats, merge_cols, loser_mapping, is_winner=0)
    
    # Print summary statistics of some rolling features for sanity check.
    print("PlayerTeam1 rolling_avg_serve_pct median:", df["PlayerTeam1.rolling_avg_serve_pct"].median())
    print("PlayerTeam2 rolling_avg_serve_pct median:", df["PlayerTeam2.rolling_avg_serve_pct"].median())
    print("PlayerTeam1 rolling_avg_bp_pct mean:", df["PlayerTeam1.rolling_avg_bp_pct"].mean())
    print("PlayerTeam2 rolling_avg_bp_pct mean:", df["PlayerTeam2.rolling_avg_bp_pct"].mean())
    print("PlayerTeam1 rolling_avg_return_pct mean:", df["PlayerTeam1.rolling_avg_return_pct"].mean())
    print("PlayerTeam2 rolling_avg_return_pct mean:", df["PlayerTeam2.rolling_avg_return_pct"].mean())
    return df


def handle_na(df: pd.DataFrame) -> pd.DataFrame:
    """Drop any remaining NA rows."""
    return df.dropna()


def convert_to_ints(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert categorical variables to dummy/indicator variables.
    Also convert certain binary flag columns to integers.
    """
    categorical_columns = ["EventType", "Court", "InOutdoor", "PlayerTeam2.PlayHand", "PlayerTeam1.PlayHand", "PlayerTeam2.Backhand", "PlayerTeam1.Backhand"]
    df = pd.get_dummies(df, columns=categorical_columns, dtype=int)
    
    # binary_columns = [
    #     "PlayerTeam1.SglRollTie", "PlayerTeam1.SglRaceTie", "PlayerTeam1.DblRollTie",
    #     "PlayerTeam2.SglRollTie", "PlayerTeam2.SglRaceTie", "PlayerTeam2.DblRollTie"
    # ]
    # for col in binary_columns:
    #     df[col] = df[col].astype(int)
    return df


def pre_drop_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Drop columns that are not useful for training."""
    cols_to_drop = [
        "IsDoubles", "RoundName", "CourtName", "LastServer", "DateSeq", "IsQualifier",
        "ScoringSystem", "EntryStatusPlayerTeam", "GamePointsPlayerTeam", "PlayerTeam1.SeedPlayerTeam"
    ]
    for col in df.columns:
        for bad in cols_to_drop:
            if bad in col:
                df = df.drop(columns=[col])
    # Filter out rows with specific reasons and ensure columns have more than one unique value.
    df = df[~df['Reason'].isin(['RET', 'DEF'])]
    df = df[df['PlayerTeam1.Sets[1].Stats'].isna()]
    df = df.loc[:, df.nunique() > 1]
    return df


def get_swap_dictionary(df: pd.DataFrame) -> Dict[str, str]:
    """Create a dictionary mapping PlayerTeam1 columns to PlayerTeam2 columns and vice versa."""
    swap_dict = {}
    for col in df.columns:
        if "PlayerTeam1" in col:
            swap_dict[col] = "PlayerTeam2" + col[11:]
        elif "PlayerTeam2" in col:
            swap_dict[col] = "PlayerTeam1" + col[11:]
    return swap_dict


def swap_and_add(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create a mirrored copy of the data by swapping player columns,
    then concatenate with the original for data augmentation.
    """
    df_copy = df.copy(deep=True)
    swap_dict = get_swap_dictionary(df)
    df_copy = df_copy.rename(columns=swap_dict)
    # Adjust the outcome: if PlayerTeam2 won in the original, then swapped PlayerTeam1 wins become 0.
    df_copy["PlayerTeam1.won"] = 1
    df_copy.loc[df_copy["PlayerTeam2.won"] == 1, "PlayerTeam1.won"] = 0
    df_copy = df_copy.drop(columns=["PlayerTeam2.won"])
    return pd.concat([df, df_copy])


def retrieve_latest_ranking(player_rankings: Dict, player_id: str, current_date: datetime) -> Any:
    """
    Retrieve the most recent ranking for a player before the current_date.
    """
    if player_id not in player_rankings:
        return None
    player_history = player_rankings[player_id]["History"]
    for item in player_history:
        rank_date = datetime.strptime(item["RankDate"][:10], "%Y-%m-%d")
        if rank_date < current_date:
            return PlayerRank(item)
    return None


def append_score_columns(player_rank: PlayerRank, prefix: str, row: Dict) -> Dict:
    """
    Append ranking score columns to the row dictionary.
    """
    for key, value in player_rank.__dict__.items():
        row[f"{prefix}{key}"] = value
    return row


def process_row(row: pd.Series, player_rankings: Dict) -> Dict:
    """
    Process a single row, appending the latest ranking info for each player.
    """
    current_date = row["StartDate"]
    player_1_id = row["PlayerTeam1.PlayerId"]
    player_2_id = row["PlayerTeam2.PlayerId"]

    row_dict = row.to_dict()
    p1_rank = retrieve_latest_ranking(player_rankings, player_1_id, current_date)
    p2_rank = retrieve_latest_ranking(player_rankings, player_2_id, current_date)
    
    if p1_rank is not None:
        row_dict = append_score_columns(p1_rank, "PlayerTeam1.", row_dict)
    if p2_rank is not None:
        row_dict = append_score_columns(p2_rank, "PlayerTeam2.", row_dict)
    return row_dict


def add_rankings_to_dataset(df: pd.DataFrame, player_rankings: Dict) -> pd.DataFrame:
    """
    Augment the dataset with ranking information using a vectorized apply.
    """
    df["StartDate"] = pd.to_datetime(df["StartDate"].str[:10], format="%Y-%m-%d")
    updated_rows = df.apply(lambda row: process_row(row, player_rankings), axis=1, result_type="expand")
    updated_df = pd.DataFrame(updated_rows)
    joblib.dump(updated_df, "./data/atp_with_rankings.pkl")
    return updated_df

def cols_to_remove_before_training(df: pd.DataFrame) -> pd.DataFrame:
    """Remove columns that contain unwanted keywords."""
    bad_words = [
        "Sets[", "TournamentName", "Doubles", "Singles", "EventYear", "EventId",
        "Round", "Time", "Winner", "Winning", "NumberOfSets", "MatchId", "TournamentCity",
        "Id", "Name", "Country", "match_id", "pct1", "TourneyLocation", "Tie",
        "opponent_factor", "date", "ProYear", "Height", "Weight", "year", "Age"
    ]
    for col in list(df.columns):
        if any(bad in col for bad in bad_words):
            df = df.drop(columns=[col])
    return df

def compute_surface_stats(df, num_years):
    """Create new stats for each type of surface"""
    new_df = df.copy()
    court_groups = df.groupby("Court")
    indoor_groups = df.groupby("InOutdoor")
    groups = itertools.chain(court_groups, indoor_groups)
    for surface_type, group in groups:
        player_stats, stats_columns = retrieve_player_stats(group, num_years)
        w_prefix = "PlayerTeam1." +  surface_type
        l_prefix = "PlayerTeam2." + surface_type

        winner_columns = get_new_column_names(stats_columns, w_prefix)
        loser_columns = get_new_column_names(stats_columns, l_prefix)
        winner_rename_mapping = get_rename_mapping(stats_columns, w_prefix)
        loser_rename_mapping = get_rename_mapping(stats_columns, l_prefix)
        columns_to_merge_on = stats_columns + ["match_id"]
        new_df = merge_dataframes(new_df, player_stats, columns_to_merge_on, winner_rename_mapping, 1)
        new_df = merge_dataframes(new_df, player_stats, columns_to_merge_on, loser_rename_mapping, 0)
        new_df = fill_na_columns(new_df, winner_columns + loser_columns, 0)

    df = new_df
    return df

def home_field_advantage(df):
    df[['TournamentCity', 'TournamentCountry']] = df['TourneyLocation'].str.split(', ', n=1, expand=True)
    df["TournamentCity"] = df["TournamentCity"].str.lower()
    df["TournamentCountry"] = df["TournamentCountry"].str.lower()
    df["PlayerTeam1.Country"] = df[PLAYER1_COUNTRY_CODE].map(country_mapping).str.lower()
    df["PlayerTeam2.Country"] = df[PLAYER2_COUNTRY_CODE].map(country_mapping).str.lower()
    df["PlayerTeam1.homefield"] = 0
    df["PlayerTeam2.homefield"] = 0

    df.loc[df["PlayerTeam1.Country"] == df["TournamentCountry"], "PlayerTeam1.homefield"] = 1
    df.loc[df["PlayerTeam2.Country"] == df["TournamentCountry"], "PlayerTeam2.homefield"] = 1
    
    # print(df["PlayerTeam1.homefield"].describe())
    # print(df["PlayerTeam2.homefield"].describe())
    return df

def compute_time_since_last_tournament(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each player (both for PlayerTeam1 and PlayerTeam2), compute the number of days since
    their previous tournament (based on the tournament StartDate) and add these as new features.
    
    Note:
      - This function processes each player's tournament history in chronological order,
        ensuring that only past tournaments are used in the calculation.
      - The start date cannot be equal to the current start date.
    """
    df["StartDate"] = pd.to_datetime(df["StartDate"], errors="coerce")

    def compute_for_player(group: pd.DataFrame, player_prefix: str) -> pd.DataFrame:
        group = group.sort_values("StartDate").reset_index(drop=True)
        days_since = []
        
        for i in range(len(group)):
            current_date = group.loc[i, "StartDate"]
            # Find the max date that is less than the current date
            previous_date = group.loc[group["StartDate"] < current_date, "StartDate"].max()
            if pd.isna(previous_date):
                days_since.append(0)  # No previous date
            else:
                days_since.append((current_date - previous_date).days)
        
        group[f"{player_prefix}.days_since_last"] = days_since
        return group

    # Apply for both PlayerTeam1 and PlayerTeam2
    df = df.groupby("PlayerTeam1.PlayerId", group_keys=False).apply(
        lambda grp: compute_for_player(grp, "PlayerTeam1")
    )
    df = df.groupby("PlayerTeam2.PlayerId", group_keys=False).apply(
        lambda grp: compute_for_player(grp, "PlayerTeam2")
    )
    
    return df

# ======================================================
# Main Pipeline
# ======================================================
def main() -> None:
    write_player_ranking_db = False
    if write_player_ranking_db:
        df_raw = joblib.load("./data/atp_stats.pkl")
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_columns', None)
        df_raw = pre_drop_cols(df_raw)
        player_rankings = joblib.load("./data/player_rankings.pkl")
        add_rankings_to_dataset(df_raw, player_rankings)
        return

    df = joblib.load("./data/atp_with_rankings.pkl")
    df = home_field_advantage(df)
    
    pd.set_option('display.max_rows', 500)
    pd.set_option('display.max_columns', 500)
    # print("Before filtering:", df.shape)
    # print(df.describe())
    df = df[df[PLAYER1_SERVE_TOTAL] > 0]
    df = df[df[PLAYER2_SERVE_TOTAL] > 0]
    df = df[df[PLAYER1_RETURN_TOTAL] > 0]
    df = df[df[PLAYER2_RETURN_TOTAL] > 0]
    # print("After filtering:", df.shape)
    # print(df.describe())
    # print("DF IS only: ", len(df))
    #print(df.isna().sum())
    df = add_features(df)
    df = compute_surface_stats(df, 3)
    df = compute_time_since_last_tournament(df)
    # Set outcome for PlayerTeam1.won (1 for winner, 0 otherwise)
    df["PlayerTeam1.won"] = 0  
    df["PlayerTeam1.PlayerId"] = df["PlayerTeam1.PlayerId"].astype(str)
    df["WinningPlayerId"] = df["WinningPlayerId"].astype(str)
    df.loc[df["PlayerTeam1.PlayerId"] == df["WinningPlayerId"], "PlayerTeam1.won"] = 1
    cutoff_date = pd.to_datetime("2000-01-01")

    df = df[df["StartDate"] >= cutoff_date]
    df = cols_to_remove_before_training(df)
    df = convert_to_ints(df)

    df = handle_na(df)

    df = swap_and_add(df)
    
    print("Final dataset length:", len(df))
    print("Missing values per column:\n", df.isna().sum())
    print("Dataset summary:\n", df.describe(include="all"))
    print(list(df.columns))
    
    joblib.dump(df, "./data/preprocessed_df.pkl")

if __name__ == "__main__":
    main()
