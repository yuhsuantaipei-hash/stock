# ========================================
# 檔案名稱：fetcher.py
# 功能說明：負責從 TWSE 抓取股價資料並在失敗時切換 yfinance。
# ========================================
from __future__ import annotations

from datetime import date
from time import sleep

import pandas as pd
import requests
import yfinance as yf

from config import REQUEST_TIMEOUT, TWSE_API_URL


MAX_RETRIES = 2


class TWSEFetchError(Exception):
    """TWSE 資料抓取失敗時拋出的例外。

    參數：
        message：描述 TWSE 查詢失敗原因的錯誤訊息。

    回傳值：
        無；此類別用於被 raise 與 except 捕捉。
    """


def _iter_months(start_date: date, end_date: date) -> list[tuple[int, int]]:
    """列出查詢區間涵蓋的年月。

    參數：
        start_date：查詢起始日期。
        end_date：查詢結束日期。

    回傳值：
        由 (西元年, 月份) 組成的清單。
    """
    current = date(start_date.year, start_date.month, 1)
    last = date(end_date.year, end_date.month, 1)
    months: list[tuple[int, int]] = []

    # 逐月前進，確保跨年區間也能完整涵蓋。
    while current <= last:
        months.append((current.year, current.month))
        next_month = current.month + 1
        next_year = current.year + (next_month - 1) // 12
        current = date(next_year, ((next_month - 1) % 12) + 1, 1)

    return months


def _parse_twse_date(value: str) -> pd.Timestamp:
    """將 TWSE 民國年日期轉為 pandas Timestamp。

    參數：
        value：TWSE 回傳的民國年日期字串，例如 113/01/02。

    回傳值：
        轉換後的 pandas Timestamp 日期物件。
    """
    year_text, month_text, day_text = str(value).split("/")
    # TWSE 使用民國年，因此需加上 1911 轉為西元年。
    return pd.Timestamp(year=int(year_text) + 1911, month=int(month_text), day=int(day_text))


def _validate_stock_id(stock_id: str) -> None:
    """檢查股票代號是否為純數字。

    參數：
        stock_id：使用者輸入的股票代號。

    回傳值：
        無；格式錯誤時拋出 ValueError。
    """
    # 僅允許純數字，避免傳入 .TW 或其他非 TWSE stockNo 格式。
    if not stock_id.isdigit():
        raise ValueError("股票代號必須為純數字")


def fetch_twse(stock_id: str, year: int, month: int) -> pd.DataFrame:
    """呼叫 TWSE API 抓取單一股票單月資料。

    參數：
        stock_id：台股股票代號，例如 2330。
        year：西元年份。
        month：月份，範圍為 1 至 12。

    回傳值：
        TWSE 原始欄位組成的 DataFrame。
    """
    _validate_stock_id(stock_id)
    query_date = f"{year}{month:02d}01"

    try:
        # TWSE API 以每月第一天作為查詢月份參數。
        response = requests.get(
            TWSE_API_URL,
            params={"response": "json", "date": query_date, "stockNo": stock_id},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as error:
        # 將 requests 例外統一包裝為 TWSEFetchError，方便上層切換備援來源。
        raise TWSEFetchError(str(error)) from error

    data = payload.get("data")
    fields = payload.get("fields")
    if payload.get("stat") != "OK" or not data or not fields:
        raise TWSEFetchError(payload.get("stat", "TWSE 未回傳有效資料"))

    return pd.DataFrame(data, columns=fields)


def _download_yfinance(stock_id: str, start_date: date, end_date: date) -> pd.DataFrame:
    """使用 yfinance 下載台股歷史資料。

    參數：
        stock_id：台股股票代號，例如 2330。
        start_date：下載起始日期。
        end_date：下載結束日期。

    回傳值：
        yfinance 欄位組成的 DataFrame。
    """
    # 數字代碼的預設備援先使用上市 .TW ticker。
    return fetch_yfinance_data(f"{stock_id}.TW", start_date, end_date)


def fetch_yfinance_data(ticker: str, start_date: date, end_date: date) -> pd.DataFrame:
    """使用完整 yfinance ticker 抓取指定日期區間股價資料。

    參數：
        ticker：yfinance 使用的完整台股代號，例如 2330.TW 或 8069.TWO。
        start_date：查詢起始日期。
        end_date：查詢結束日期。

    回傳值：
        yfinance 欄位組成的 DataFrame。
    """
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            # 使用完整 ticker，可支援上市 .TW 與上櫃 .TWO。
            data = yf.download(
                ticker,
                start=start_date,
                end=end_date,
                auto_adjust=False,
                progress=False,
                threads=True,
                timeout=REQUEST_TIMEOUT,
            )

            # yfinance 有時會回傳 MultiIndex，先攤平成一般欄位。
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            return data.reset_index()
        except Exception as error:
            last_error = error
            if attempt < MAX_RETRIES:
                # 短暫等待後重試，降低暫時性網路錯誤影響。
                sleep(1)

    raise RuntimeError(f"yfinance 查詢失敗：{last_error}")


def fetch_stock_data(stock_id: str, start_date: date, end_date: date) -> tuple[pd.DataFrame, str]:
    """依月份抓取 TWSE 資料，任一月份失敗時整體改用 yfinance。

    參數：
        stock_id：台股股票代號，例如 2330。
        start_date：查詢起始日期。
        end_date：查詢結束日期。

    回傳值：
        二元組，第一個元素為股價 DataFrame，第二個元素為資料來源字串。
    """
    _validate_stock_id(stock_id)

    try:
        # TWSE 一次查一個月份，因此依查詢區間逐月合併。
        frames = [fetch_twse(stock_id, year, month) for year, month in _iter_months(start_date, end_date)]
        merged_data = pd.concat(frames, ignore_index=True)

        # TWSE 回傳整月資料，需再依使用者輸入日期區間過濾。
        parsed_dates = merged_data["日期"].map(_parse_twse_date)
        date_mask = (parsed_dates.dt.date >= start_date) & (parsed_dates.dt.date <= end_date)
        return merged_data.loc[date_mask].reset_index(drop=True), "TWSE"
    except TWSEFetchError:
        # 任一月份失敗就整體切換 yfinance，避免混用不同來源資料。
        fallback_data = _download_yfinance(stock_id, start_date, end_date)
        return fallback_data, "yfinance"
