import streamlit as st
import xml.etree.ElementTree as ET
import re
import pandas as pd
import io

# XML名前空間を登録
ET.register_namespace('xml', 'http://www.w3.org/XML/1998/namespace')

st.set_page_config(page_title="TMX分析ツール", layout="wide")
st.title("TMX分析ツール")
st.subheader("日本語訳と英語原文の英単語の「単複の違い」を確認") # サブヘッダーを更新

uploaded_file = st.file_uploader("TMXファイルをアップロード", type=["tmx"])

# 除外ペアの入力エリア
with st.expander("除外設定", expanded=False):
    st.markdown("""
    ### 除外する原語・訳語ペアの設定

    以下の形式で除外したいペアを入力してください。各行に「原語,訳語」の形式で入力します。
    これにより、意図的な単複の変更を「差異」として検出しなくなります。

    #### 基本的な使い方
    - 例: `example,examples` (原文が単数形、訳文が複数形の場合を除外)
    - 例: `web,Web` (このツールでは検出しませんが、他のケースで利用可能)

    #### 正規表現の使用方法
    正規表現を使用する場合は、パターンの前に `r:` を付けてください。
    - 例: `r:\\b\\w+[^s]s\\b,r:\\b\\w+\\b` （原語に複数形の単語があり、訳語が単数形の単語がある場合を除外）

    **注意**: 正規表現で `\\` のように特殊文字をエスケープする必要があります。

    **デフォルトの除外ペアについて**:
    VMs/VM、CPUs/CPU などは正規表現 `r:[A-Z][A-Z]+s,r:[A-Z][A-Z]+` で除外されています。
    """)
    
    default_exclusion_pairs = """r:[A-Z][A-Z]+s,r:[A-Z][A-Z]+
bean,Bean
cookie,Cookie
egress,Egress
ingress,Ingress
personal access token,Personal Access Token
playbook,Playbook
pod,Pod
web,Web
We,Red Hat
vCPU,仮想 CPU
VIP,仮想 IP
manual page,man ページ
"""
    
    exclusion_pairs_text = st.text_area(
        "除外ペア (各行に「原語,訳語」の形式で入力)",
        value=default_exclusion_pairs,
        height=150,
        help="各行に「原語,訳語」の形式で入力。大文字小文字は区別されます。"
    )
    
    exclusion_pairs = []
    if exclusion_pairs_text:
        for line in exclusion_pairs_text.strip().split('\n'):
            if line and ',' in line:
                source, target = line.split(',', 1)
                exclusion_pairs.append((source.strip(), target.strip()))
    
    if exclusion_pairs:
        st.info(f"設定された除外ペア数: {len(exclusion_pairs)}")
    else:
        st.info("除外ペアが設定されていません")

def extract_english_words(text):
    words = re.findall(r'\b[a-zA-Z]{2,}\b', text)
    return words

def get_full_text_content(element):
    if element is None:
        return ""
    text = element.text or ""
    for child in element:
        text += get_full_text_content(child)
        if child.tail:
            text += child.tail
    return text

def should_exclude(en_text, ja_text, exclusion_pairs):
    for source, target in exclusion_pairs:
        source_is_regex = source.startswith('r:')
        target_is_regex = target.startswith('r:')
        source_pattern = source[2:] if source_is_regex else re.escape(source)
        target_pattern = target[2:] if target_is_regex else re.escape(target)
        
        try:
            source_match = bool(re.search(source_pattern, en_text))
            target_match = bool(re.search(target_pattern, ja_text))
            if source_match and target_match:
                return True
        except re.error as e:
            st.warning(f"正規表現エラー: {str(e)} - パターン: '{source_pattern}' または '{target_pattern}'")
            continue
    return False

def are_singular_plural_pair(word1, word2):
    w1_lower = word1.lower()
    w2_lower = word2.lower()

    if w1_lower == w2_lower:
        return False

    irregular_map = {
        "child": "children", "man": "men", "woman": "women", "tooth": "teeth",
        "foot": "feet", "mouse": "mice", "goose": "geese", "ox": "oxen",
        "person": "people", "die": "dice", "corpus": "corpora", "focus": "foci",
        "datum": "data", "medium": "media", "analysis": "analyses", "basis": "bases",
        "criterion": "criteria", "phenomenon": "phenomena", "index": "indices", 
        "thesis": "theses", "radius": "radii", "formula": "formulae", 
        "shelf": "shelves", "leaf": "leaves", "knife": "knives", "life": "lives", "wolf": "wolves"
    }
    if irregular_map.get(w1_lower) == w2_lower or irregular_map.get(w2_lower) == w1_lower:
        return True

    if w1_lower + 's' == w2_lower: return True
    if w1_lower.endswith('y') and len(w1_lower) > 1 and w1_lower[-2] not in 'aeiou' and w1_lower[:-1] + 'ies' == w2_lower: return True
    if any(w1_lower.endswith(s) for s in ['s', 'x', 'z', 'ch', 'sh', 'o']) and w1_lower + 'es' == w2_lower: return True
    if (w1_lower.endswith('f') and not w1_lower.endswith('ff')) and w1_lower[:-1] + 'ves' == w2_lower: return True 
    if w1_lower.endswith('fe') and w1_lower[:-2] + 'ves' == w2_lower: return True

    if w2_lower + 's' == w1_lower: return True
    if w2_lower.endswith('y') and len(w2_lower) > 1 and w2_lower[-2] not in 'aeiou' and w2_lower[:-1] + 'ies' == w1_lower: return True
    if any(w2_lower.endswith(s) for s in ['s', 'x', 'z', 'ch', 'sh', 'o']) and w2_lower + 'es' == w1_lower: return True
    if (w2_lower.endswith('f') and not w2_lower.endswith('ff')) and w2_lower[:-1] + 'ves' == w1_lower: return True
    if w2_lower.endswith('fe') and w2_lower[:-2] + 'ves' == w1_lower: return True
    
    return False

def analyze_tmx(file_content, exclusion_pairs):
    try:
        tree = ET.parse(io.BytesIO(file_content))
        root = tree.getroot()
        
        results = []
        excluded_count = 0
        
        tus = root.findall(".//tu") or root.findall(".//{*}tu")
        
        for idx, tu in enumerate(tus, 1):
            en_text = ""
            ja_text = ""
            
            segs = tu.findall(".//seg") or tu.findall(".//{*}seg")
            for seg in segs:
                parent = None
                for parent_elem in tu:
                    if seg in parent_elem.iter():
                        parent = parent_elem
                        break
                
                lang = None
                if parent is not None:
                    lang = parent.get("xml:lang") or parent.get("{http://www.w3.org/XML/1998/namespace}lang")
                    if lang is None:
                        for attr_name, attr_value in parent.attrib.items():
                            if attr_name.endswith('lang'):
                                lang = attr_value
                                break
                
                text_content = get_full_text_content(seg)
                if lang == "en-us" or lang == "en":
                    en_text = text_content
                elif lang == "ja" or lang == "ja-jp":
                    ja_text = text_content
            
            if en_text and ja_text:
                if exclusion_pairs and should_exclude(en_text, ja_text, exclusion_pairs):
                    excluded_count += 1
                    continue

                en_words_original_case = extract_english_words(en_text)
                ja_eng_words_in_translation = extract_english_words(ja_text)

                en_words_set_original = set(en_words_original_case)
                singular_plural_differences = []

                for ja_word in ja_eng_words_in_translation:
                    if ja_word in en_words_set_original: # 完全一致の場合はスキップ
                        continue
                    
                    # 完全一致でない場合、原文中の各単語と単複ペアをチェック
                    for en_word_orig_from_src in en_words_original_case:
                        if are_singular_plural_pair(ja_word, en_word_orig_from_src):
                            singular_plural_differences.append(f"{en_word_orig_from_src}/{ja_word}")
                            break # この日本語単語に対する単複ペアが見つかったので次へ
                
                # 全てのセグメントを結果に追加（差異がない場合も含む）
                results.append({
                    "ID": idx,
                    "英語原文": en_text,
                    "日本語訳": ja_text,
                    "単複のみの違い": ", ".join(singular_plural_differences) if singular_plural_differences else "なし",
                    "要確認(単複のみの違い)": len(singular_plural_differences) > 0,
                })
        
        if excluded_count > 0:
            st.info(f"除外条件に一致したセグメント数: {excluded_count}")
        
        if not results:
            # このメッセージは、TU自体が見つからなかった場合など
            st.warning("分析対象の翻訳ペアが見つかりませんでした。TMXファイルの構造を確認してください。")
            return None
            
        return pd.DataFrame(results)
    except Exception as e:
        st.error(f"エラーが発生しました: {str(e)}")
        import traceback
        st.code(traceback.format_exc())
        return None

if uploaded_file is not None:
    file_content = uploaded_file.read()
    
    with st.spinner("TMXファイルを分析中..."):
        df = analyze_tmx(file_content, exclusion_pairs)
    
    if df is not None and not df.empty:
        singular_plural_count = df["要確認(単複のみの違い)"].sum()
        
        st.metric("要確認 (単複のみの違い)", f"{singular_plural_count} / {len(df)}") # メトリクスを1つに
        
        st.subheader("分析結果")
        
        filter_option = st.radio(
            "表示オプション:",
            ["すべて表示", 
             "要確認のみ(単複のみの違い)"], # フィルタオプションを削減
            index=1, # デフォルトを「要確認のみ(単複のみの違い)」に
            horizontal=True
        )
        
        if filter_option == "要確認のみ(単複のみの違い)":
            filtered_df = df[df["要確認(単複のみの違い)"] == True]
        else: # すべて表示
            filtered_df = df
        
        base_columns = ["ID", "英語原文", "日本語訳"]
        # 表示列を「単複のみの違い」に固定
        columns_to_display = base_columns + ["単複のみの違い"]
            
        display_df = filtered_df[columns_to_display].copy()
        
        if display_df.empty:
            if filter_option == "すべて表示" and not df.empty : # df自体にデータはあるが、フィルタ結果が空(通常は起こりにくいが念のため)
                 st.info("分析対象となる翻訳ペアはありましたが、指定の差異は見つかりませんでした。")
            elif filter_option == "要確認のみ(単複のみの違い)":
                 st.info(f"「{filter_option}」に該当するデータはありませんでした。")
            # dfがもともと空の場合は analyze_tmx でメッセージ表示
        else:
            html = """
            <style>
                .styled-table { border-collapse: collapse; width: 100%; font-size: 14px; text-align: left; }
                .styled-table th { background-color: #f2f2f2; color: #333; font-weight: bold; padding: 10px 8px; border: 1px solid #ddd; }
                .styled-table td { padding: 8px; border: 1px solid #ddd; word-wrap: break-word; max-width: 400px; }
                .styled-table tr:nth-child(even) { background-color: #f9f9f9; }
                .styled-table tr:nth-child(odd) { background-color: #ffffff; }
                .styled-table tr:hover { background-color: #e6f7ff; }
                .index-column { width: 50px; text-align: center; font-weight: bold; }
                .no-issue-cell { color: green; }
            </style>
            <table class="styled-table"><thead><tr>
            """
            for col in display_df.columns:
                html += f"<th class='{'index-column' if col == 'ID' else ''}'>{col}</th>"
            html += "</tr></thead><tbody>"

            for _, row in display_df.iterrows():
                html += "<tr>"
                for col_name in display_df.columns:
                    cell_value = str(row[col_name]) 
                    cell_class = "index-column" if col_name == "ID" else ""
                    if cell_value == "なし" and col_name == "単複のみの違い": # "なし"のスタイル適用対象を限定
                        cell_class += " no-issue-cell"
                    html += f"<td class='{cell_class.strip()}'>{cell_value}</td>"
                html += "</tr>"
            html += "</tbody></table>"
            st.write(html, unsafe_allow_html=True)
            
            csv = display_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="CSV形式でダウンロード",
                data=csv,
                file_name="tmx_analysis_result_sp_diff.csv", # ファイル名を変更
                mime="text/csv"
            )
    elif df is None and uploaded_file: 
        # analyze_tmx内でエラー表示済み、または「差異なし」のメッセージ表示済みの場合
        pass
    elif df is not None and df.empty: # analyze_tmx が空のDFを返した場合 (TUなしなど)
        st.info("分析対象となる翻訳ペアが見つかりませんでした。") # analyze_tmx内のメッセージと重複する可能性あり
    elif not uploaded_file:
        st.info("TMXファイルをアップロードして分析を開始してください。")


with st.expander("使い方"):
    st.markdown("""
    ### このアプリケーションの使い方
    
    1. 上部の「Browse files」ボタンをクリックしてTMXファイルをアップロードします。
    2. 必要に応じて「除外設定」で、特定の原文/訳文ペア（意図的な単複の変更など）を分析対象から除外します。
    3. アプリが自動的にファイルを分析し、結果を表示します。
    4. **結果の概要**: 「単複のみの違い」で「要確認」と判断されたセグメントの数が表示されます。
    5. **分析結果テーブル**:
        - **ID**: 翻訳ユニットの通し番号。
        - **英語原文**: TMXファイル内の英語原文。
        - **日本語訳**: TMXファイル内の日本語訳。
        - **単複のみの違い**: 日本語訳中の英単語が、英語原文の単語と単数形・複数形のみ異なる場合、そのペア (`原文の形/訳文の形`)。原文に完全一致する単語が訳文にある場合は、ここでは差異として検出しません。
    6. **表示オプション**: テーブルに表示するセグメントをフィルタリングできます。
        - **すべて表示**: すべての翻訳セグメントを表示します。
        - **要確認のみ(単複のみの違い)**: 「単複のみの違い」が検出されたセグメントのみを表示します（デフォルト）。
    7. 分析結果はCSV形式でダウンロードできます。
    
    ### 「要確認」の判断基準
    - **要確認(単複のみの違い)**: 「単複のみの違い」列にペアが1つ以上リストアップされた場合。
    
    ### 英単語の抽出ルール
    - アルファベットが2文字以上連続するものを英単語として抽出します。
    """)
