# ========================================
# 檔案名稱：error_handler.py
# 功能說明：將查詢與資料處理例外轉換為友善錯誤訊息。
# ========================================
from __future__ import annotations

import requests

from fetcher import TWSEFetchError


def handle_fetch_error(e: Exception) -> str:
    """將查詢例外轉換為友善的繁體中文錯誤訊息。

    參數：
        e：查詢、網路或資料處理過程中捕捉到的例外。

    回傳值：
        適合顯示在 Streamlit 介面上的繁體中文錯誤訊息。
    """
    # 先處理網路連線問題，讓使用者知道可以檢查連線狀態。
    if isinstance(e, (ConnectionError, requests.ConnectionError)):
        return "網路連線失敗，請確認網路狀態後重試"

    # TWSE 失敗通常會嘗試備援資料來源，因此訊息保持友善。
    if isinstance(e, TWSEFetchError):
        return "TWSE 查詢失敗，已切換備援資料來源"

    # 股票代號格式錯誤由 ValueError 統一回報。
    if isinstance(e, ValueError):
        return "股票代號格式錯誤，請輸入純數字（例如：2330）"

    # 其他未預期錯誤保留原始訊息，方便除錯。
    return f"系統發生未知錯誤：{str(e)}"
