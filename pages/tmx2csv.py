# 必要なライブラリ
# pip install streamlit pandas translate-toolkit openpyxl
import streamlit as st
import pandas as pd
import io
import zipfile
import math
from translate.storage import tmx

# ページの基本設定
st.set_page_config(page_title="TMX 変換ツール", layout="wide")
st.title("TMX 分割・変換ツール")
st.subheader("TMXファイルをCSVまたはExcel形式でダウンロード（分割機能付き）")

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

def create_zip_file(df_chunks, file_format):
    """
    分割されたDataFrameのリストからZIPファイルをメモリ上に生成する
    :param df_chunks: DataFrameのリスト
    :param file_format: 'csv' または 'excel'
    :return: ZIPファイルのバイナリデータ (bytes)
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for i, chunk in enumerate(df_chunks):
            part_num = i + 1
            
            if file_format == 'csv':
                file_name = f"tmx_export_part{part_num}.csv"
                file_data = convert_df_to_csv(chunk)
            elif file_format == 'excel':
                file_name = f"tmx_export_part{part_num}.xlsx"
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

# --- メイン処理 ---

# ファイルアップローダー
uploaded_file = st.file_uploader("TMXファイルをアップロード", type=["tmx"])

if uploaded_file is not None:
    file_content = uploaded_file.read()
    
    with st.spinner("TMXファイルを処理中..."):
        df = extract_data_from_tmx(file_content)
    
    # データの抽出に成功した場合
    if df is not None and not df.empty:
        total_rows = len(df)
        st.success(f"{total_rows} 件の翻訳ペアを抽出しました。")
        
        st.subheader("プレビュー（先頭10件）")
        st.dataframe(df.head(10))
        
        st.divider()
        
        # --- 分割設定 ---
        st.subheader("ダウンロード設定")
        split_files = st.checkbox("ファイルを分割する", value=False)
        
        max_rows = 10000 # デフォルト値
        
        if split_files:
            max_rows = st.number_input(
                "1ファイルあたりの最大行数", 
                min_value=1, 
                value=max(1, min(10000, total_rows)), # デフォルト値は10000行か全行数の少ない方
                step=1000
            )
            
            num_files = math.ceil(total_rows / max_rows)
            st.info(f"設定に基づき、{num_files} 個のファイルに分割されます。")
            
            # DataFrameを分割
            df_chunks = [df.iloc[i:i + max_rows] for i in range(0, total_rows, max_rows)]
        else:
            # 分割しない場合も、リストに格納して処理を共通化
            df_chunks = [df]

        st.divider()

        # --- ダウンロードボタン ---
        col1, col2 = st.columns(2)
        
        # --- 1. CSV形式 ---
        with col1:
            if split_files:
                # 分割（ZIP）
                csv_zip_data = create_zip_file(df_chunks, 'csv')
                st.download_button(
                    label="CSV (ZIP) 形式でダウンロード",
                    data=csv_zip_data,
                    file_name="tmx_export_csv.zip",
                    mime="application/zip",
                    use_container_width=True
                )
            else:
                # 単一ファイル
                csv_data = convert_df_to_csv(df)
                st.download_button(
                    label="CSV形式でダウンロード",
                    data=csv_data,
                    file_name="tmx_export.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        # --- 2. Excel (.xlsx) 形式 ---
        with col2:
            try:
                if split_files:
                    # 分割（ZIP）
                    excel_zip_data = create_zip_file(df_chunks, 'excel')
                    st.download_button(
                        label="Excel (ZIP) 形式でダウンロード",
                        data=excel_zip_data,
                        file_name="tmx_export_excel.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
                else:
                    # 単一ファイル
                    excel_data = convert_df_to_excel(df)
                    st.download_button(
                        label="Excel (.xlsx) 形式でダウンロード",
                        data=excel_data,
                        file_name="tmx_export.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
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
    2. 処理が完了すると、抽出件数とプレビューが表示されます。
    3. **ダウンロード設定:**
        * そのままダウンロードする場合は、CSVまたはExcelボタンをクリックします。
        * **ファイルを分割する場合:** 「ファイルを分割する」にチェックを入れ、1ファイルあたりの最大行数を指定します。
    4. 対応する「(ZIP) 形式でダウンロード」ボタンをクリックすると、分割されたファイルがZIPにまとめられてダウンロードされます。
    """)