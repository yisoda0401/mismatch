# 必要なライブラリ
# pip install streamlit pandas translate-toolkit openpyxl
import streamlit as st
import pandas as pd
import io
import zipfile
import math
import os
from translate.storage import tmx

# ページの基本設定
st.set_page_config(page_title="TMX 検索・分割・変換ツール", layout="wide")
st.title("TMX 検索・分割・変換ツール")
st.subheader("TMXファイルをCSVまたはExcel形式でダウンロード（検索・分割機能付き）")

# --- ヘルパー関数 (ZIP生成) ---

def convert_df_to_csv(df):
    """DataFrameをBOM付きUTF-8 CSV (bytes) に変換"""
    return df.to_csv(index=False).encode('utf-8-sig')

def convert_df_to_excel(df):
    """DataFrameをExcel (bytes) に変換"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='TMX_Export')
    return output.getvalue()

def create_zip_file(df_chunks, file_format, base_name):
    """
    分割されたDataFrameのリストからZIPファイルをメモリ上に生成する
    :param df_chunks: DataFrameのリスト
    :param file_format: 'csv' または 'excel'
    :param base_name: 出力ファイルのベース名（拡張子なし）
    :return: ZIPファイルのバイナリデータ (bytes)
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for i, chunk in enumerate(df_chunks):
            part_num = i + 1
            
            if file_format == 'csv':
                file_name = f"{base_name}_part{part_num}.csv"
                file_data = convert_df_to_csv(chunk)
            elif file_format == 'excel':
                file_name = f"{base_name}_part{part_num}.xlsx"
                file_data = convert_df_to_excel(chunk)
            else:
                continue
                
            zip_file.writestr(file_name, file_data)
            
    return zip_buffer.getvalue()

# --- TMX解析関数 ---

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
                    "Source (en-us)": en_text,
                    "Target (ja)": ja_text,
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

# --- メイン処理 ---

# ファイルアップローダー
uploaded_file = st.file_uploader("TMXファイルをアップロード", type=["tmx"])

if uploaded_file is not None:
    file_content = uploaded_file.read()
    
    # 入力ファイル名からベース名（拡張子なし）を取得
    base_name = os.path.splitext(uploaded_file.name)[0]
    
    with st.spinner("TMXファイルを処理中..."):
        df = extract_data_from_tmx(file_content)
    
    # データの抽出に成功した場合
    if df is not None and not df.empty:
        total_rows = len(df)
        st.success(f"{total_rows} 件の翻訳ペアを抽出しました。")
        
        st.divider()
        
        # --- 検索機能 ---
        st.subheader("🔍 検索")
        
        search_col1, search_col2 = st.columns([3, 1])
        with search_col1:
            search_query = st.text_input(
                "検索キーワード",
                placeholder="原文または訳文から検索...",
                help="入力したキーワードを含む翻訳ペアをフィルタリングします"
            )
        with search_col2:
            search_target = st.selectbox(
                "検索対象",
                options=["原文のみ", "訳文のみ", "原文と訳文両方"],
                index=0
            )
        
        # 大文字小文字を区別するかどうか
        case_sensitive = st.checkbox("大文字・小文字を区別する", value=False)
        
        # 検索フィルタリング
        if search_query:
            if case_sensitive:
                if search_target == "原文のみ":
                    mask = df["Source (en-us)"].str.contains(search_query, na=False, regex=False)
                elif search_target == "訳文のみ":
                    mask = df["Target (ja)"].str.contains(search_query, na=False, regex=False)
                else:  # 原文と訳文両方
                    mask = (
                        df["Source (en-us)"].str.contains(search_query, na=False, regex=False) |
                        df["Target (ja)"].str.contains(search_query, na=False, regex=False)
                    )
            else:
                if search_target == "原文のみ":
                    mask = df["Source (en-us)"].str.contains(search_query, case=False, na=False, regex=False)
                elif search_target == "訳文のみ":
                    mask = df["Target (ja)"].str.contains(search_query, case=False, na=False, regex=False)
                else:  # 原文と訳文両方
                    mask = (
                        df["Source (en-us)"].str.contains(search_query, case=False, na=False, regex=False) |
                        df["Target (ja)"].str.contains(search_query, case=False, na=False, regex=False)
                    )
            
            filtered_df = df[mask]
            st.info(f"🔎 「{search_query}」の検索結果: {len(filtered_df)} 件 / {total_rows} 件")
        else:
            filtered_df = df
        
        st.divider()
        
        # --- プレビュー/検索結果表示 ---
        if search_query:
            st.subheader(f"検索結果（{len(filtered_df)} 件）")
            if not filtered_df.empty:
                st.dataframe(filtered_df, hide_index=True, width="stretch")
            else:
                st.warning("検索条件に一致するデータがありません。")
        else:
            st.subheader("プレビュー（先頭10件）")
            st.dataframe(df.head(10), hide_index=True)
        
        st.divider()
        
        # --- 分割設定 ---
        st.subheader("ダウンロード設定")
        
        # ダウンロード対象の行数を表示
        download_rows = len(filtered_df)
        if search_query:
            st.caption(f"📥 ダウンロード対象: 検索結果 {download_rows} 件")
        else:
            st.caption(f"📥 ダウンロード対象: 全データ {download_rows} 件")
        
        split_files = st.checkbox("ファイルを分割する", value=False)
        
        max_rows = 10000 # デフォルト値
        
        if split_files:
            max_rows = st.number_input(
                "1ファイルあたりの最大行数", 
                min_value=1, 
                value=max(1, min(10000, download_rows)), # デフォルト値は10000行かダウンロード対象行数の少ない方
                step=1000
            )
            
            num_files = math.ceil(download_rows / max_rows)
            st.info(f"設定に基づき、{num_files} 個のファイルに分割されます。")
            
            # DataFrameを分割（検索結果を対象）
            df_chunks = [filtered_df.iloc[i:i + max_rows] for i in range(0, download_rows, max_rows)]
        else:
            # 分割しない場合も、リストに格納して処理を共通化（検索結果を対象）
            df_chunks = [filtered_df]

        st.divider()

        # --- ダウンロードボタン ---
        col1, col2 = st.columns(2)
        
        # --- 1. CSV形式 ---
        with col1:
            if split_files:
                # 分割（ZIP）
                csv_zip_data = create_zip_file(df_chunks, 'csv', base_name)
                st.download_button(
                    label="CSV (ZIP) 形式でダウンロード",
                    data=csv_zip_data,
                    file_name=f"{base_name}_csv.zip",
                    mime="application/zip",
                    width="stretch"
                )
            else:
                # 単一ファイル
                csv_data = convert_df_to_csv(filtered_df)
                st.download_button(
                    label="CSV形式でダウンロード",
                    data=csv_data,
                    file_name=f"{base_name}.csv",
                    mime="text/csv",
                    width="stretch"
                )
        
        # --- 2. Excel (.xlsx) 形式 ---
        with col2:
            try:
                if split_files:
                    # 分割（ZIP）
                    excel_zip_data = create_zip_file(df_chunks, 'excel', base_name)
                    st.download_button(
                        label="Excel (ZIP) 形式でダウンロード",
                        data=excel_zip_data,
                        file_name=f"{base_name}_excel.zip",
                        mime="application/zip",
                        width="stretch"
                    )
                else:
                    # 単一ファイル
                    excel_data = convert_df_to_excel(filtered_df)
                    st.download_button(
                        label="Excel (.xlsx) 形式でダウンロード",
                        data=excel_data,
                        file_name=f"{base_name}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        width="stretch"
                    )
            except ImportError:
                with col2:
                    st.error("Excelの書き出しに必要な 'openpyxl' が見つかりません。")
            except Exception as e:
                with col2:
                    st.error(f"Excel生成エラー: {str(e)}")

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
    1. 上部の「Browse files」ボタンをクリックして、変換したいTMXファイル（`.tmx`）をアップロードします。
    2. 処理が完了すると、抽出件数が表示されます。
    3. **検索機能（オプション）:**
        * 「検索キーワード」に文字列を入力すると、データをフィルタリングできます。
        * **検索対象**: 「原文のみ」「訳文のみ」「原文と訳文両方」から選択できます。
        * **大文字・小文字を区別する**: チェックを入れると、大文字・小文字を区別して検索します。
        * 検索結果はそのままダウンロードできます。
    4. **ダウンロード設定:**
        * そのままダウンロードする場合は、CSVまたはExcelボタンをクリックします。
        * **ファイルを分割する場合:** 「ファイルを分割する」にチェックを入れ、1ファイルあたりの最大行数を指定します。
    5. 対応する「(ZIP) 形式でダウンロード」ボタンをクリックすると、分割されたファイルがZIPにまとめられてダウンロードされます。
    """)