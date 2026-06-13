# ========================================
# 檔案名稱：charts.py
# 功能說明：建立 K 線圖、成交量圖與收盤價折線圖。
# ========================================
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def plot_candlestick(df: pd.DataFrame, stock_id: str) -> go.Figure:
    """建立含 MA5 與 MA20 的 K 線圖。

    參數：
        df：已清洗並含有日期、OHLC、MA5、MA20 欄位的 DataFrame。
        stock_id：股票代號，用於圖表標題。

    回傳值：
        Plotly Figure K 線圖物件。
    """
    figure = go.Figure()

    # 主圖使用台灣慣例：上漲紅色、下跌綠色。
    figure.add_trace(
        go.Candlestick(
            x=df["日期"],
            open=df["開盤價"],
            high=df["最高價"],
            low=df["最低價"],
            close=df["收盤價"],
            name="K 線",
            increasing_line_color="red",
            decreasing_line_color="green",
        )
    )

    # MA5 使用橘色虛線，方便辨識短期趨勢。
    figure.add_trace(
        go.Scatter(
            x=df["日期"],
            y=df["MA5"],
            mode="lines",
            name="MA5",
            line={"color": "orange", "dash": "dash"},
        )
    )

    # MA20 使用藍色虛線，方便辨識中期趨勢。
    figure.add_trace(
        go.Scatter(
            x=df["日期"],
            y=df["MA20"],
            mode="lines",
            name="MA20",
            line={"color": "blue", "dash": "dash"},
        )
    )

    figure.update_layout(
        title=f"{stock_id} 股價走勢（K 線圖）",
        xaxis_title="日期",
        yaxis_title="股價",
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
    )
    return figure


def plot_volume(df: pd.DataFrame, stock_id: str) -> go.Figure:
    """建立成交量長條圖，並依漲跌日套用台灣慣例顏色。

    參數：
        df：已清洗並含有日期、開盤價、收盤價、成交量欄位的 DataFrame。
        stock_id：股票代號，用於圖表標題。

    回傳值：
        Plotly Figure 成交量長條圖物件。
    """
    # 收盤價大於等於開盤價視為上漲日，以紅色標示。
    colors = ["red" if close_price >= open_price else "green" for open_price, close_price in zip(df["開盤價"], df["收盤價"])]

    figure = go.Figure()
    figure.add_trace(go.Bar(x=df["日期"], y=df["成交量"], marker_color=colors, name="成交量"))
    figure.update_layout(
        title=f"{stock_id} 成交量",
        xaxis_title="日期",
        yaxis_title="成交量",
        hovermode="x unified",
    )
    return figure


def plot_close_line(df: pd.DataFrame, stock_id: str) -> go.Figure:
    """建立收盤價折線圖。

    參數：
        df：已清洗並含有日期與收盤價欄位的 DataFrame。
        stock_id：股票代號，用於圖表標題。

    回傳值：
        Plotly Figure 收盤價折線圖物件。
    """
    figure = go.Figure()

    # 折線圖用於快速觀察查詢區間內的收盤價變化。
    figure.add_trace(go.Scatter(x=df["日期"], y=df["收盤價"], mode="lines", name="收盤價"))
    figure.update_layout(
        title=f"{stock_id} 收盤價走勢",
        xaxis_title="日期",
        yaxis_title="收盤價",
        hovermode="x unified",
    )
    return figure
