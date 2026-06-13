# ========================================
# 檔案名稱：app.py
# 功能說明：建立 Streamlit 台灣股市資料查詢系統主介面。
# ========================================
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from charts import plot_candlestick, plot_close_line, plot_volume
from config import CACHE_TTL, MAX_DATE_RANGE_DAYS
from error_handler import handle_fetch_error
from exporter import convert_df_to_csv
from fetcher import fetch_stock_data, fetch_yfinance_data
from processor import process_data
from stock_history_lookup import StockInfo, resolve_stock_keyword


def configure_page() -> None:
    """設定 Streamlit 頁面資訊。

    參數：
        無。

    回傳值：
        無。
    """
    # 設定寬版版面，讓圖表有足夠水平空間顯示。
    st.set_page_config(page_title="台灣股市資料查詢系統", page_icon="📈", layout="wide")


def _fetch_by_resolved_stock(stock_info: StockInfo, start_date: date, end_date: date) -> tuple[pd.DataFrame, str]:
    """依解析後的股票資訊抓取原始資料。

    參數：
        stock_info：由中文名稱或股票代碼解析出的股票資訊。
        start_date：查詢起始日期。
        end_date：查詢結束日期。

    回傳值：
        二元組，第一個元素為原始資料，第二個元素為資料來源。
    """
    if stock_info.market == "TWSE":
        # 上市股優先走 TWSE 月資料 API。
        return fetch_stock_data(stock_info.code, start_date, end_date)

    if stock_info.market == "TPEX":
        # 上櫃股使用 yfinance 的 .TWO ticker。
        return fetch_yfinance_data(stock_info.ticker, start_date, end_date), "yfinance"

    raw_data, source = fetch_stock_data(stock_info.code, start_date, end_date)
    if not process_data(raw_data, source).empty:
        return raw_data, source

    # 無法從清單判斷市場時，若 .TW 無資料再嘗試 .TWO。
    return fetch_yfinance_data(f"{stock_info.code}.TWO", start_date, end_date), "yfinance"


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_stock_data(search_keyword: str, start_date: date, end_date: date) -> tuple[pd.DataFrame, str, str]:
    """快取股票查詢、中文名稱解析與資料清洗結果。

    參數：
        search_keyword：股票中文名稱或股票代號，例如台積電或 2330。
        start_date：查詢起始日期。
        end_date：查詢結束日期。

    回傳值：
        三元組，包含已清洗資料、資料來源與顯示用股票名稱。
    """
    stock_info = resolve_stock_keyword(search_keyword)
    if stock_info is None:
        raise LookupError("找不到此公司，請檢查名稱是否正確")

    # 先解析中文名稱或代碼，再依市場別選擇資料來源。
    raw_data, source = _fetch_by_resolved_stock(stock_info, start_date, end_date)
    display_name = f"{stock_info.code} {stock_info.name}"
    return process_data(raw_data, source), source, display_name


def render_sidebar() -> dict[str, str | date] | None:
    """繪製側邊欄並回傳查詢條件。

    參數：
        無。

    回傳值：
        使用者最近一次送出的查詢條件；尚未查詢時回傳 None。
    """
    today = date.today()
    default_start_date = today - timedelta(days=90)

    with st.sidebar:
        st.header("查詢條件")
        stock_keyword = st.text_input("股票代號或公司名稱", value="2330", placeholder="例如：2330、台積電、鴻海")
        start_date = st.date_input("起始日期", value=default_start_date)
        end_date = st.date_input("結束日期", value=today)
        query_clicked = st.button("查詢", type="primary", use_container_width=True)

        # 清除快取可強制重新向資料來源查詢。
        if st.button("清除快取", use_container_width=True):
            st.cache_data.clear()
            st.success("快取已清除")

        # 顯示最近一次成功查詢的資料來源。
        if "data_source" in st.session_state:
            st.info(f"資料來源：{st.session_state['data_source']}")

    if query_clicked:
        # 使用 session_state 保留查詢條件，避免下載或圖表互動後畫面清空。
        st.session_state["query"] = {
            "stock_keyword": stock_keyword.strip(),
            "start_date": start_date,
            "end_date": end_date,
        }

    return st.session_state.get("query")


def validate_dates(start_date: date, end_date: date) -> bool:
    """驗證查詢日期區間是否有效。

    參數：
        start_date：查詢起始日期。
        end_date：查詢結束日期。

    回傳值：
        日期區間有效時回傳 True，否則回傳 False。
    """
    # 起始日期晚於結束日期時立即中止查詢。
    if start_date > end_date:
        st.error("起始日期不得晚於結束日期")
        return False

    # 限制最大查詢天數，避免一次抓取過多月份造成等待過久。
    if (end_date - start_date).days > MAX_DATE_RANGE_DAYS:
        st.error(f"查詢區間不可超過 {MAX_DATE_RANGE_DAYS} 天")
        return False

    return True


def render_metrics(stock_label: str, start_date: date, end_date: date, source: str, df: pd.DataFrame) -> None:
    """繪製股票代號、查詢區間與資料摘要資訊卡。

    參數：
        stock_label：股票代號與公司名稱。
        start_date：查詢起始日期。
        end_date：查詢結束日期。
        source：資料來源字串。
        df：已清洗的股價資料。

    回傳值：
        無。
    """
    # 最新收盤價取排序後最後一筆資料。
    latest_close = df["收盤價"].iloc[-1] if not df.empty else None

    metric_columns = st.columns(4)
    metric_columns[0].metric("股票", stock_label)
    metric_columns[1].metric("查詢區間", f"{start_date} 至 {end_date}")
    metric_columns[2].metric("資料來源", source)
    metric_columns[3].metric("最新收盤價", f"{latest_close:,.2f}" if latest_close is not None else "無資料")


def render_results(stock_label: str, start_date: date, end_date: date, df: pd.DataFrame, source: str) -> None:
    """繪製查詢結果、圖表、資料表與 CSV 下載。

    參數：
        stock_label：股票代號與公司名稱。
        start_date：查詢起始日期。
        end_date：查詢結束日期。
        df：已清洗的股價資料。
        source：資料來源字串。

    回傳值：
        無。
    """
    render_metrics(stock_label, start_date, end_date, source, df)

    # 依序顯示 K 線、成交量與收盤價折線圖。
    st.plotly_chart(plot_candlestick(df, stock_label), use_container_width=True)
    st.plotly_chart(plot_volume(df, stock_label), use_container_width=True)
    st.plotly_chart(plot_close_line(df, stock_label), use_container_width=True)

    # 資料表只顯示最近 30 筆，避免主畫面過長。
    st.subheader("最近 30 筆資料")
    st.dataframe(df.sort_values("日期", ascending=False).head(30), use_container_width=True, hide_index=True)

    # 提供完整清洗後資料下載。
    st.download_button(
        "下載 CSV",
        data=convert_df_to_csv(df),
        file_name=f"{stock_label.replace(' ', '_')}_stock_data.csv",
        mime="text/csv",
        use_container_width=True,
    )


def main() -> None:
    """執行台灣股市資料查詢系統主程式。

    參數：
        無。

    回傳值：
        無。
    """
    configure_page()
    st.title("台灣股市資料查詢系統")

    query = render_sidebar()
    if query is None:
        st.info("請輸入查詢條件後按下「查詢」。")
        return

    stock_keyword = str(query["stock_keyword"])
    start_date = query["start_date"]
    end_date = query["end_date"]

    if not validate_dates(start_date, end_date):
        return

    try:
        # 所有查詢操作集中在 try/except，錯誤交由 error_handler 顯示。
        with st.spinner("資料查詢中..."):
            processed_data, source, stock_label = load_stock_data(stock_keyword, start_date, end_date)

        st.session_state["data_source"] = source
        st.sidebar.info(f"資料來源：{source}")

        if processed_data.empty:
            st.error("查無交易資料，請調整股票代號或查詢日期。")
            return

        render_results(stock_label, start_date, end_date, processed_data, source)
    except LookupError as error:
        st.error(str(error))
    except Exception as error:
        st.error(handle_fetch_error(error))


if __name__ == "__main__":
    main()
