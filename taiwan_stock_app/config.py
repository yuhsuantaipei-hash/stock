# ========================================
# 檔案名稱：config.py
# 功能說明：集中管理 API、快取、日期範圍與欄位對應設定。
# ========================================
from __future__ import annotations

TWSE_API_URL = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"
REQUEST_TIMEOUT = 10
CACHE_TTL = 300
MAX_DATE_RANGE_DAYS = 365

COLUMN_MAP = {
    "日期": "日期",
    "開盤價": "開盤價",
    "最高價": "最高價",
    "最低價": "最低價",
    "收盤價": "收盤價",
    "成交股數": "成交量",
    "成交金額": "成交金額",
    "漲跌價差": "漲跌價差",
    "本益比": "本益比",
}
