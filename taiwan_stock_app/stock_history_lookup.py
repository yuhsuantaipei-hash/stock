# ========================================
# 檔案名稱：stock_history_lookup.py
# 功能說明：支援中文名稱或股票代碼查詢並匯出台股一年歷史股價。
# ========================================
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import StringIO
from time import sleep

import pandas as pd
import requests
import yfinance as yf


TWSE_LIST_URL = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
TPEX_LIST_URL = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
REQUEST_TIMEOUT = 10
MAX_RETRIES = 2
USER_AGENT = "Mozilla/5.0 (compatible; TaiwanStockHistoryLookup/1.0)"


@dataclass(frozen=True)
class StockInfo:
    """儲存台股基本識別資訊。

    參數：
        code：股票代碼。
        name：股票中文名稱。
        market：市場別，支援 TWSE 或 TPEX。
        ticker：yfinance 使用的完整代號。

    回傳值：
        無；此類別用於保存不可變股票資訊。
    """

    code: str
    name: str
    market: str
    ticker: str


def fetch_stock_list(url: str, market: str) -> pd.DataFrame:
    """從證交所 ISIN 頁面抓取上市或上櫃股票清單。

    參數：
        url：上市或上櫃清單網址。
        market：市場別，TWSE 表示上市，TPEX 表示上櫃。

    回傳值：
        包含 code、name、market、ticker 欄位的 DataFrame。
    """
    response = requests.get(url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()

    # ISIN 頁面是 Big5 編碼，明確指定可避免中文亂碼。
    response.encoding = "big5"
    tables = pd.read_html(StringIO(response.text))
    raw_table = tables[0]
    raw_table.columns = raw_table.iloc[0]
    raw_table = raw_table.iloc[1:].copy()

    records: list[dict[str, str]] = []
    for raw_value in raw_table["有價證券代號及名稱"].dropna():
        text = str(raw_value).strip()
        parts = text.split(maxsplit=1)

        # 只保留代碼為純數字的普通股票資料。
        if len(parts) != 2 or not parts[0].isdigit():
            continue

        code, name = parts
        suffix = ".TW" if market == "TWSE" else ".TWO"
        records.append({"code": code, "name": name, "market": market, "ticker": f"{code}{suffix}"})

    return pd.DataFrame(records)


@lru_cache(maxsize=1)
def load_stock_directory() -> pd.DataFrame:
    """一次性載入上市與上櫃股票清單。

    參數：
        無。

    回傳值：
        合併上市與上櫃股票資訊的 DataFrame。
    """
    # 程式啟動後第一次查詢才載入，後續透過 lru_cache 重用本地清單。
    twse_list = fetch_stock_list(TWSE_LIST_URL, "TWSE")
    tpex_list = fetch_stock_list(TPEX_LIST_URL, "TPEX")
    return pd.concat([twse_list, tpex_list], ignore_index=True)


def resolve_stock_keyword(search_keyword: str) -> StockInfo | None:
    """將中文名稱或數字代碼解析為 yfinance 台股代號。

    參數：
        search_keyword：使用者輸入的中文公司名稱或股票代碼。

    回傳值：
        找到時回傳 StockInfo；找不到中文名稱時回傳 None。
    """
    keyword = search_keyword.strip()
    if not keyword:
        raise ValueError("查詢關鍵字不可為空")

    stock_directory = load_stock_directory()

    if keyword.isdigit():
        matched_rows = stock_directory[stock_directory["code"] == keyword]
        if not matched_rows.empty:
            row = matched_rows.iloc[0]
            return StockInfo(code=row["code"], name=row["name"], market=row["market"], ticker=row["ticker"])

        # 清單無法判斷上市或上櫃時，先預設使用 .TW，後續若無資料再試 .TWO。
        return StockInfo(code=keyword, name=keyword, market="UNKNOWN", ticker=f"{keyword}.TW")

    exact_matches = stock_directory[stock_directory["name"] == keyword]
    if not exact_matches.empty:
        row = exact_matches.iloc[0]
        return StockInfo(code=row["code"], name=row["name"], market=row["market"], ticker=row["ticker"])

    # 中文名稱允許部分比對，例如輸入「台積」也可找到「台積電」。
    contains_matches = stock_directory[stock_directory["name"].str.contains(keyword, na=False)]
    if not contains_matches.empty:
        row = contains_matches.iloc[0]
        return StockInfo(code=row["code"], name=row["name"], market=row["market"], ticker=row["ticker"])

    print("找不到此公司，請檢查名稱是否正確")
    return None


def download_history_with_retry(ticker: str) -> pd.DataFrame:
    """使用 yfinance 下載過去一年每日歷史股價並支援重試。

    參數：
        ticker：yfinance 使用的股票代號，例如 2330.TW。

    回傳值：
        yfinance 回傳的歷史股價 DataFrame。
    """
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            # yfinance timeout 設為 10 秒，避免網路卡住太久。
            data = yf.download(
                ticker,
                period="1y",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=True,
                timeout=REQUEST_TIMEOUT,
            )

            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

            return data
        except Exception as error:
            last_error = error
            if attempt < MAX_RETRIES:
                # 短暫等待後重試，降低暫時性連線失敗影響。
                sleep(1)

    raise RuntimeError(f"抓取 yfinance 資料失敗：{last_error}")


def normalize_history_data(df: pd.DataFrame) -> pd.DataFrame:
    """整理 yfinance 歷史股價欄位與日期格式。

    參數：
        df：yfinance 回傳的原始歷史股價 DataFrame。

    回傳值：
        欄位整理後且日期格式為 YYYY-MM-DD 的 DataFrame。
    """
    if df.empty:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])

    normalized_data = df.reset_index().copy()
    normalized_data["Date"] = pd.to_datetime(normalized_data["Date"]).dt.strftime("%Y-%m-%d")

    # 僅保留需求指定欄位，避免匯出多餘資訊。
    selected_columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
    return normalized_data[selected_columns]


def export_history_to_csv(df: pd.DataFrame, keyword: str) -> str:
    """將歷史股價匯出為 CSV 檔案。

    參數：
        df：已整理的歷史股價 DataFrame。
        keyword：使用者輸入的公司名稱或代碼，用於組成檔名。

    回傳值：
        已產生的 CSV 檔案名稱。
    """
    safe_keyword = keyword.strip().replace("/", "_").replace("\\", "_")
    filename = f"{safe_keyword}_historical_data.csv"

    # 使用 UTF-8 BOM，避免 Excel 開啟中文檔名或欄位時亂碼。
    df.to_csv(filename, index=False, encoding="utf-8-sig")
    return filename


def get_taiwan_stock_data(search_keyword: str) -> pd.DataFrame | None:
    """依中文名稱或股票代碼抓取台股過去一年每日歷史股價。

    參數：
        search_keyword：中文公司名稱或數字股票代碼，例如「台積電」或「2330」。

    回傳值：
        成功時回傳已整理的歷史股價 DataFrame；找不到公司或抓取失敗時回傳 None。
    """
    try:
        stock_info = resolve_stock_keyword(search_keyword)
        if stock_info is None:
            return None

        tickers_to_try = [stock_info.ticker]
        if stock_info.market == "UNKNOWN":
            # 代碼無法判斷市場時，先試 .TW，無資料再試 .TWO。
            tickers_to_try.append(f"{stock_info.code}.TWO")

        normalized_data = pd.DataFrame()
        used_ticker = ""
        for ticker in tickers_to_try:
            history_data = download_history_with_retry(ticker)
            normalized_data = normalize_history_data(history_data)
            used_ticker = ticker
            if not normalized_data.empty:
                break

        if normalized_data.empty:
            print("警告：日期區間內完全無資料，可能遇到假日、停牌或資料來源暫無資料。")
        else:
            filename = export_history_to_csv(normalized_data, search_keyword)
            print(f"已匯出 {stock_info.name}（{used_ticker}）歷史股價：{filename}")

        return normalized_data
    except ValueError as error:
        print(f"輸入錯誤：{error}")
    except requests.RequestException as error:
        print(f"清單抓取失敗，請稍後再試：{error}")
    except Exception as error:
        print(f"抓取失敗，請稍後再試：{error}")

    return None


def main() -> None:
    """提供命令列互動查詢入口。

    參數：
        無。

    回傳值：
        無。
    """
    keyword = input("請輸入公司中文名稱或股票代碼：").strip()
    data = get_taiwan_stock_data(keyword)

    # 顯示前五筆資料，方便使用者確認查詢結果。
    if data is not None and not data.empty:
        print(data.head())


if __name__ == "__main__":
    main()
