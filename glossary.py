import streamlit as st
import pandas as pd
from lxml import etree
from tqdm.auto import tqdm
import io
import csv

st.set_page_config(page_title="TMX 用語検出ツール", layout="wide")

# ---------- ヘルプ ----------
st.sidebar.title("使い方")
st.sidebar.markdown("""
1. **CSV**（用語集）をアップロード  
2. **TMX** ファイルをアップロード  
3. 検索列名を指定（デフォルトは `term`）  
4. 「検索」ボタンで処理開始  
5. 結果を確認・ダウンロード
""")

# ---------- アップロード ----------
csv_file = st.file_uploader("CSV ファイル (用語集) をアップロード", type=["csv"])
tmx_file = st.file_uploader("TMX ファイルをアップロード", type=["tmx"])

if csv_file and tmx_file:
    # -------- CSV 読み込み ----------
    try:
        df_terms = pd.read_csv(csv_file, encoding='utf-8')
        if 'term' not in df_terms.columns:
            st.warning("CSV に `term` 列が見つかりません。列名を確認してください。")
        else:
            terms_set = set(df_terms['term'].dropna().astype(str).str.strip())
            st.success(f"用語数: {len(terms_set)} 件読み込み完了")
    except Exception as e:
        st.error(f"CSV 読み込みエラー: {e}")

    # -------- TMX 解析 ----------
    target_lang = st.text_input("検索対象言語コード（例: ja）", value="ja")

    if 'terms_set' in locals():
        with st.spinner('TMX を解析中…'):
            try:
                parser = etree.XMLParser(recover=True, encoding='utf-8')
                tree = etree.parse(tmx_file, parser)
                root = tree.getroot()
               
                # TMX の構造は <tmx><body><tu>... になることが多い
                tu_elements = root.findall('.//{*}tu')
                total_segments = len(tu_elements)

                results = []
                for idx, tu in enumerate(tqdm(tu_elements, desc="解析中", unit="TU")):
                    source_seg = None
                    target_seg = None

                    for tuv in tu.findall('{*}tuv'):
                        lang = tuv.get("{http://www.w3.org/XML/1998/namespace}lang")
                        seg_el = tuv.find('{*}seg')
                        if seg_el is not None:
                            text = seg_el.text or ""
                            if lang == target_lang:
                                target_seg = text
                            else:
                                source_seg = text

                    # 検索
                    found_terms = [t for t in terms_set if t in (target_seg or "")]
                    if found_terms:
                        results.append({
                            'idx': idx + 1,
                            'source': source_seg,
                            'target': target_seg,
                            'terms_found': ', '.join(found_terms)
                        })

                st.success(f"検索完了: {len(results)} 件が該当")
               
                # ---------- 結果表示 ----------
                if results:
                    df_res = pd.DataFrame(results)
                    st.dataframe(df_res, use_container_width=True)

                    # CSV ダウンロード
                    csv_buffer = io.StringIO()
                    df_res.to_csv(csv_buffer, index=False)
                    st.download_button(
                        label="該当セグメントを CSV でダウンロード",
                        data=csv_buffer.getvalue(),
                        file_name="matched_segments.csv",
                        mime="text/csv"
                    )
                else:
                    st.info("該当する用語は見つかりませんでした。")

            except Exception as e:
                st.error(f"TMX 解析エラー: {e}")