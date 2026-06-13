# ========================================
# 檔案名稱：processor.py
# 功能說明：清洗股價資料並計算 MA5 與 MA20 技術指標。
# ========================================
from __future__ import annotations

import pandas as pd

from config import COLUMN_MAP


FINAL_COLUMNS = ["日期", "開盤價", "最高價", "最低價", "收盤價", "成交量", "MA5", "MA20"]


def _parse_twse_date(value: str) -> pd.Timestamp:
    """將 TWSE 民國年日期轉為 datetime。

    參數：
        value：TWSE 回傳的民國年日期字串。

    回傳值：
        轉換後的 pandas Timestamp。
    """
    year_text, month_text, day_text = str(value).split("/")
    # 民國年轉西元年，讓後續排序與圖表顯示一致。
    return pd.Timestamp(year=int(year_text) + 1911, month=int(month_text), day=int(day_text))


def _clean_numeric(series: pd.Series) -> pd.Series:
    """移除千分位逗號並轉換為 float。

    參數：
        series：包含數字字串或數值的 pandas Series。

    回傳值：
        已轉為數值型態的 pandas Series。
    """
    # TWSE 數值常含千分位逗號，需先移除再轉型。
    cleaned_series = series.astype(str).str.replace(",", "", regex=False).str.replace("--", "", regex=False)
    return pd.to_numeric(cleaned_series, errors="coerce")


def _rename_yfinance_columns(df: pd.DataFrame) -> pd.DataFrame:
    """將 yfinance 欄位轉為繁體中文標準欄位。

    參數：
        df：yfinance 回傳的原始 DataFrame。

    回傳值：
        欄位名稱已轉為繁體中文標準欄位的 DataFrame。
    """
    # 僅重新命名系統需要的欄位，其餘欄位會在最後輸出時排除。
    return df.rename(
        columns={
            "Date": "日期",
            "Open": "開盤價",
            "High": "最高價",
            "Low": "最低價",
            "Close": "收盤價",
            "Volume": "成交量",
        }
    )


def process_data(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """依資料來源清洗股價資料並計算 MA5 與 MA20。

    參數：
        df：TWSE 或 yfinance 回傳的原始股價資料。
        source：資料來源字串，支援 TWSE 或 yfinance。

    回傳值：
        欄位標準化並包含 MA5、MA20 的 DataFrame。
    """
    if df.empty:
        return pd.DataFrame(columns=FINAL_COLUMNS)

    processed_data = df.copy()

    # 不同資料來源欄位命名不同，先統一成繁體中文標準欄位。
    if source == "TWSE":
        processed_data = processed_data.rename(columns=COLUMN_MAP)
        processed_data["日期"] = processed_data["日期"].map(_parse_twse_date)
    elif source == "yfinance":
        processed_data = _rename_yfinance_columns(processed_data)
        processed_data["日期"] = pd.to_datetime(processed_data["日期"])
    else:
        raise ValueError(f"不支援的資料來源：{source}")

    numeric_columns = ["開盤價", "最高價", "最低價", "收盤價", "成交量"]
    for column in numeric_columns:
        if column in processed_data.columns:
            # 價格與成交量需轉成 float，後續才能計算均線與繪圖。
            processed_data[column] = _clean_numeric(processed_data[column])

    # 移除缺少日期或收盤價的資料，避免圖表產生空點。
    processed_data = processed_data.dropna(subset=["日期", "收盤價"])

    # 成交量為 0 視為非交易資料列，依規格過濾。
    processed_data = processed_data[processed_data["成交量"].fillna(0) > 0]
    processed_data = processed_data.sort_values("日期").reset_index(drop=True)

    # 計算短期與中期移動平均線，供 K 線圖疊加顯示。
    processed_data["MA5"] = processed_data["收盤價"].rolling(window=5).mean()
    processed_data["MA20"] = processed_data["收盤價"].rolling(window=20).mean()

    return processed_data[FINAL_COLUMNS]
