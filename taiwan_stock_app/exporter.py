# ========================================
# 檔案名稱：exporter.py
# 功能說明：將查詢結果轉換為可下載的 CSV 位元資料。
# ========================================
from __future__ import annotations

import pandas as pd


def convert_df_to_csv(df: pd.DataFrame) -> bytes:
    """將 DataFrame 轉為 UTF-8 BOM CSV bytes。

    參數：
        df：要匯出的股價資料 DataFrame。

    回傳值：
        可供 st.download_button 使用的 CSV bytes。
    """
    # 使用 UTF-8 BOM，避免 Excel 開啟繁體中文時出現亂碼。
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
