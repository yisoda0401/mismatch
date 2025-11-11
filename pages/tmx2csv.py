# 必要なライブラリ
# pip install streamlit pandas translate-toolkit
import streamlit as st
import pandas as pd
import io
from translate.storage import tmx

# ページの基本設定
st.set_page_config(page_title="TMX to CSV 変換ツール", layout="wide")
st.title("TMX to CSV 変換ツール")
st.subheader("TMXファイルの英語原文と日本語訳をCSV形式でダウンロード")

# ファイルアップローダー
uploaded_file = st.file_uploader("TMXファイルをアップロード", type=["tmx"])

def extract_data_from_tmx(file_content):
    """
    TMXファイルの内容を解析し、原文と訳文のペアを抽出する関数。
    """
    try:
        tmx_file_obj = io.BytesIO(file_content)
        tmx_file = tmx.tmxfile(tmx_file_obj)
        
        results = []
        
        # TMXファイル内の各翻訳ユニット(unit)をループ処理
        for idx, unit in enumerate(tmx_file.units, 1):
            en_text = unit.source
            ja_text = unit.target
            
            # 原文と訳文の両方が存在する場合のみリストに追加
            if en_text and ja_text:
                results.append({
                    "ID": idx,
                    "英語原文 (Source)": en_text,
                    "日本語訳 (Target)": ja_text,
                })
        
        if not results:
            st.warning("翻訳ペアが見つかりませんでした。TMXファイルの構造を確認してください。")
            return None
            
        return pd.DataFrame(results)
    except Exception as e:
        st.error(f"ファイルの解析中にエラーが発生しました: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
        return None

# TMXファイルがアップロードされた場合の処理
if uploaded_file is not None:
    file_content = uploaded_file.read()
    
    with st.spinner("TMXファイルを処理中..."):
        df = extract_data_from_tmx(file_content)
    
    # データの抽出に成功した場合
    if df is not None and not df.empty:
        st.success(f"{len(df)} 件の翻訳ペアを抽出しました。")
        
        st.subheader("プレビュー（先頭10件）")
        st.dataframe(df.head(10))
        
        # DataFrameをCSVに変換
        # BOM付きUTF-8 (utf-8-sig) にしてExcelでの文字化けを防ぐ
        csv = df.to_csv(index=False).encode('utf-8-sig')
        
        st.download_button(
            label="CSV形式でダウンロード",
            data=csv,
            file_name="tmx_export.csv",
            mime="text/csv",
        )

    # データが空だった場合
    elif df is not None and df.empty: 
        st.info("TMXファイルからデータを抽出できませんでした。")
    
    #
    else: 
        pass 

# ファイルがアップロードされていない場合
else:
    st.info("TMXファイルをアップロードして処理を開始してください。")

# 使い方セクション
with st.expander("使い方"):
    st.markdown("""
    1. 上部の「Browse files」ボタンをクリックして、CSVに変換したいTMXファイル（`.tmx`）をアップロードします。
    2. ファイルの処理が自動的に開始されます。
    3. 処理が完了すると、抽出された翻訳ペアの件数とプレビュー（先頭10件）が表示されます。
    4. 「CSV形式でダウンロード」ボタンをクリックすると、すべての原文と訳文のペアが含まれるCSVファイルがダウンロードされます。
    """)