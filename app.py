import streamlit as st
import xml.etree.ElementTree as ET
import re
import pandas as pd
import io

# XML名前空間を登録
ET.register_namespace('xml', 'http://www.w3.org/XML/1998/namespace')

st.set_page_config(page_title="TMX分析ツール", layout="wide")
st.title("TMX分析ツール")
st.subheader("日本語訳に含まれる英単語が英語原文に存在するか確認・分析")

uploaded_file = st.file_uploader("TMXファイルをアップロード", type=["tmx"])

# 除外ペアの入力エリア
with st.expander("除外設定", expanded=False):
    
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
manual page,man ページ"""
    
    exclusion_pairs_text = st.text_area(
        "除外ペア (各行に「原語,訳語」の形式で入力。詳細は「使い方」を参照)",
        value=default_exclusion_pairs,
        height=150,
        help="各行に「原語,訳語」の形式で入力。大文字小文字は区別されます。"
    )
    
    # 除外ペアの解析
    exclusion_pairs = []
    if exclusion_pairs_text:
        for line in exclusion_pairs_text.strip().split('\n'):
            if line and ',' in line:
                source, target = line.split(',', 1)
                exclusion_pairs.append((source.strip(), target.strip()))
    
    if exclusion_pairs:
        st.info(f"設定された除外ペア数: {len(exclusion_pairs)}")
        for source, target in exclusion_pairs:
            st.text(f"原語: '{source}' → 訳語: '{target}'")
    else:
        st.info("除外ペアが設定されていません")

def extract_english_words(text):
    # 英単語を抽出（アルファベットとアンダーバーが2文字以上連続するもの）
    words = re.findall(r'\b[a-zA-Z_]{2,}\b', text)
    return words

def get_full_text_content(element):
    """要素内のすべてのテキストを再帰的に取得（タグを無視）"""
    if element is None:
        return ""
    
    text = element.text or ""
    
    for child in element:
        text += get_full_text_content(child)
        if child.tail:
            text += child.tail
            
    return text

def is_pair_excluded(source_word, target_word, exclusion_rules):
    """指定された単語ペアが除外ルールに一致するかを判断"""
    for source_rule, target_rule in exclusion_rules:
        source_is_regex = source_rule.startswith('r:')
        target_is_regex = target_rule.startswith('r:')
        
        source_pattern = source_rule[2:] if source_is_regex else re.escape(source_rule)
        target_pattern = target_rule[2:] if target_is_regex else re.escape(target_rule)
        
        try:
            # re.fullmatch を使い、単語全体がパターンに一致するかを確認
            source_match = bool(re.fullmatch(source_pattern, source_word))
            target_match = bool(re.fullmatch(target_pattern, target_word))
            
            if source_match and target_match:
                return True
        except re.error as e:
            # UIにエラーを表示するのは冗長になる可能性があるため、ここではスキップ
            # st.warning(f"正規表現エラー: {str(e)}")
            continue
            
    return False

def are_singular_plural_pair(word1, word2):
    """2つの単語が単数形と複数形のペアであるか（大文字小文字を無視して）判定する。"""
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
        "shelf": "shelves", "leaf": "leaves", "knife": "knives", "life": "lives", "wolf": "wolves",
        "cactus": "cacti", "syllabus": "syllabi" 
    }
    if irregular_map.get(w1_lower) == w2_lower or irregular_map.get(w2_lower) == w1_lower:
        return True

    def check_regular(singular, plural):
        if singular + 's' == plural: return True
        if singular.endswith('y') and len(singular) > 1 and singular[-2].lower() not in 'aeiou' and singular[:-1] + 'ies' == plural: return True
        if any(singular.endswith(s) for s in ['s', 'x', 'z', 'ch', 'sh', 'o']) and singular + 'es' == plural: return True
        if (singular.endswith('f') and not singular.endswith('ff')) and singular[:-1] + 'ves' == plural: return True 
        if singular.endswith('fe') and singular[:-2] + 'ves' == plural: return True
        return False

    return check_regular(w1_lower, w2_lower) or check_regular(w2_lower, w1_lower)


def analyze_tmx(file_content, exclusion_pairs):
    try:
        tree = ET.parse(io.BytesIO(file_content))
        root = tree.getroot()
        
        namespaces = dict([node for _, node in ET.iterparse(io.BytesIO(file_content), events=['start-ns'])])
        if not namespaces:
            namespaces['xml'] = 'http://www.w3.org/XML/1998/namespace'
        
        results = []
        
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
                en_words_case_sensitive = extract_english_words(en_text)
                en_words_set_original = set(en_words_case_sensitive)
                
                en_words_dict_case_sensitive = {word: word for word in en_words_case_sensitive}
                en_words_dict_case_insensitive = {word.lower(): word for word in en_words_case_sensitive}
                
                ja_eng_words = extract_english_words(ja_text)
                
                # --- 差異候補をまず全て検出 ---
                potential_words_not_in_source = []
                potential_case_diffs = []
                potential_sp_diffs = []
                potential_underscore_diffs = []

                for ja_word in ja_eng_words:
                    word_lower = ja_word.lower()

                    # アンダーバーを含む単語
                    if '_' in ja_word:
                        if word_lower in en_words_dict_case_insensitive:
                            if ja_word not in en_words_dict_case_sensitive:
                                potential_underscore_diffs.append((en_words_dict_case_insensitive[word_lower], ja_word))
                        else:
                            potential_underscore_diffs.append(("-", ja_word))
                        continue

                    # アンダーバーを含まない単語
                    if word_lower not in en_words_dict_case_insensitive:
                        is_sp_pair = False
                        for en_word in en_words_case_sensitive:
                            if are_singular_plural_pair(ja_word, en_word):
                                potential_sp_diffs.append((en_word, ja_word))
                                is_sp_pair = True
                                break
                        if not is_sp_pair:
                            potential_words_not_in_source.append(ja_word)
                    elif ja_word not in en_words_dict_case_sensitive:
                        potential_case_diffs.append((en_words_dict_case_insensitive[word_lower], ja_word))

                    if ja_word not in en_words_set_original:
                        is_already_sp_pair = any(p[1] == ja_word for p in potential_sp_diffs)
                        if not is_already_sp_pair:
                            for en_word_orig in en_words_case_sensitive:
                                if are_singular_plural_pair(ja_word, en_word_orig):
                                    potential_sp_diffs.append((en_word_orig, ja_word))
                                    break
                
                # --- 除外ルールを適用して最終的な差異リストを作成 ---
                final_case_diffs = [f"{s}/{t}" for s, t in potential_case_diffs if not is_pair_excluded(s, t, exclusion_pairs)]
                final_sp_diffs = list(set([f"{s}/{t}" for s, t in potential_sp_diffs if not is_pair_excluded(s, t, exclusion_pairs)]))
                final_underscore_diffs = [f"{s}/{t}" for s, t in potential_underscore_diffs if not is_pair_excluded(s, t, exclusion_pairs)]
                
                # 「原文にない単語」はペアではないため、除外ロジックは適用しない
                final_words_not_in_source = [f"-/{w}" for w in potential_words_not_in_source]
                
                results.append({
                    "ID": idx,
                    "英語原文": en_text,
                    "日本語訳": ja_text,
                    "大/小文字違い": ", ".join(final_case_diffs) if final_case_diffs else "なし",
                    "単複の違い": ", ".join(final_sp_diffs) if final_sp_diffs else "なし", 
                    "原文にない単語": ", ".join(final_words_not_in_source) if final_words_not_in_source else "なし",
                    "アンダーバー違い": ", ".join(final_underscore_diffs) if final_underscore_diffs else "なし",
                    "要確認(大/小文字違い)": len(final_case_diffs) > 0,
                    "要確認(単複の違い)": len(final_sp_diffs) > 0,
                    "要確認(原文にない単語)": len(final_words_not_in_source) > 0,
                    "要確認(アンダーバー違い)": len(final_underscore_diffs) > 0
                })
        
        if not results:
            st.warning("翻訳ペアが見つかりませんでした。TMXファイルの構造を確認してください。")
            with st.expander("TMXファイル構造（デバッグ）"):
                xml_str = ET.tostring(root, encoding='utf-8').decode('utf-8')
                st.code(xml_str[:5000] + ("..." if len(xml_str) > 5000 else ""), language="xml")
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
        case_difference_count = df["要確認(大/小文字違い)"].sum()
        singular_plural_count = df["要確認(単複の違い)"].sum()
        not_in_source_count = df["要確認(原文にない単語)"].sum()
        underscore_count = df["要確認(アンダーバー違い)"].sum()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1: 
            st.metric("要確認 (大/小文字違い)", f"{case_difference_count} / {len(df)}")
        with col2:
            st.metric("要確認 (単複の違い)", f"{singular_plural_count} / {len(df)}")
        with col3:
            st.metric("要確認 (原文にない単語)", f"{not_in_source_count} / {len(df)}")
        with col4:
            st.metric("要確認 (アンダーバー違い)", f"{underscore_count} / {len(df)}")
        
        st.subheader("分析結果")
        
        filter_option = st.radio(
            "表示オプション:",
            ["すべて表示", 
             "大/小文字違い",
             "単複の違い",
             "原文にない単語",
             "アンダーバー違い",
             "いずれかの方法で要確認"],
            index=5, 
            horizontal=True
        )
        
        if filter_option == "大/小文字違い":
            filtered_df = df[df["要確認(大/小文字違い)"] == True]
        elif filter_option == "単複の違い":
            filtered_df = df[df["要確認(単複の違い)"] == True]
        elif filter_option == "原文にない単語":
            filtered_df = df[df["要確認(原文にない単語)"] == True]
        elif filter_option == "アンダーバー違い":
            filtered_df = df[df["要確認(アンダーバー違い)"] == True]
        elif filter_option == "いずれかの方法で要確認":
            filtered_df = df[
                             (df["要確認(原文にない単語)"] == True) | 
                             (df["要確認(大/小文字違い)"] == True) |
                             (df["要確認(単複の違い)"] == True) |
                             (df["要確認(アンダーバー違い)"] == True)
                            ]
        else:
            filtered_df = df
        
        base_columns = ["ID", "英語原文", "日本語訳"]
        
        if filter_option == "大/小文字違い":
            columns_to_display = base_columns + ["大/小文字違い"]
        elif filter_option == "単複の違い":
            columns_to_display = base_columns + ["単複の違い"]
        elif filter_option == "原文にない単語":
            columns_to_display = base_columns + ["原文にない単語"]
        elif filter_option == "アンダーバー違い":
            columns_to_display = base_columns + ["アンダーバー違い"]
        else:
            columns_to_display = base_columns + ["大/小文字違い", "単複の違い", "原文にない単語", "アンダーバー違い"]
            
        if not filtered_df.empty: 
            filtered_df_display = filtered_df[columns_to_display].copy()
        else: 
            filtered_df_display = pd.DataFrame(columns=columns_to_display)

        html = """
        <style>
            .styled-table { border-collapse: collapse; width: 100%; font-size: 14px; text-align: left; }
            .styled-table th { background-color: #f2f2f2; color: #333; font-weight: bold; padding: 10px 8px; border: 1px solid #ddd; }
            .styled-table td { padding: 8px; border: 1px solid #ddd; word-wrap: break-word; max-width: 350px; }
            .styled-table tr:nth-child(even) { background-color: #f9f9f9; }
            .styled-table tr:nth-child(odd) { background-color: #ffffff; }
            .styled-table tr:hover { background-color: #e6f7ff; }
            .index-column { width: 50px; text-align: center; font-weight: bold; }
        </style>
        <table class="styled-table"><thead><tr>
        """
        for col in filtered_df_display.columns:
            html += f"<th class='{'index-column' if col == 'ID' else ''}'>{col}</th>"
        html += "</tr></thead><tbody>"

        if not filtered_df_display.empty:
            for _, row in filtered_df_display.iterrows():
                html += "<tr>"
                for col_name in filtered_df_display.columns:
                    cell_value = str(row[col_name]) 
                    cell_class = "index-column" if col_name == "ID" else ""
                    if cell_value == "なし" and col_name in ["原文にない単語", "大/小文字違い", "単複の違い", "アンダーバー違い"]: 
                        html += f"<td class='{cell_class.strip()}' style='color: green;'>{cell_value}</td>"
                    else:
                        html += f"<td class='{cell_class.strip()}'>{cell_value}</td>"
                html += "</tr>"
        else:
             html += f"<tr><td colspan='{len(columns_to_display)}' style='text-align:center;'>該当するデータがありません。</td></tr>"
        html += "</tbody></table>"
        st.write(html, unsafe_allow_html=True)
        
        if not filtered_df_display.empty:
            csv = filtered_df_display.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="CSV形式でダウンロード",
                data=csv,
                file_name="tmx_analysis_result.csv",
                mime="text/csv"
            )
        else:
            st.info("ダウンロードするデータがありません。")

    elif df is not None and df.empty: 
        st.info("分析対象の翻訳ペアが見つかりましたが、条件に一致する項目はありませんでした。")
    else: 
        pass 
else:
    st.info("TMXファイルをアップロードして分析を開始してください。")

with st.expander("使い方"):
    st.markdown("""
    ### このアプリケーションの使い方
    
    1. 上部の「Browse files」ボタンをクリックしてTMXファイルをアップロードします。
    2. 必要に応じて「除外設定」で除外する原語・訳語ペアを設定します。
    3. アプリが自動的にファイルを分析し、結果を表示します。
    4. **分析結果の概要**: 各確認項目について、要確認と判断されたセグメント数が表示されます。
    5. **分析結果テーブル**:
        - **ID**: 翻訳ユニットの通し番号。
        - **英語原文**: TMXファイル内の英語原文。
        - **日本語訳**: TMXファイル内の日本語訳。
        - **大/小文字違い**: 日本語訳中の英単語（アンダースコアを含まない）が、大文字・小文字を区別すると英語原文に存在しないが、無視すると存在する場合に、そのペアをリストアップします (例: `Pod/pod`)。
        - **単複の違い**: 日本語訳中の英単語（アンダースコアを含まない）が、英語原文の単語と単数形・複数形のみ異なる場合に、そのペアをリストアップします (例: `book/books`)。
        - **原文にない単語**: 日本語訳中の英単語（アンダースコアを含まない）が、大文字・小文字を無視しても英語原文に存在しない場合に、`- / 訳文の単語` の形式でリストアップします (例: `-/word`)。
        - **アンダーバー違い**: アンダースコアを含む単語の差異を `原文/訳文` 形式でリストアップします (例: `MY_VAR/my_var`, `-/new_var`)。
    6. **表示オプション**: テーブルに表示するセグメントをフィルタリングできます。
    7. 分析結果はCSV形式でダウンロードできます。
    
    ### 「要確認」の判断基準
    - 各「要確認」列にペアが1つ以上リストアップされた場合に、それぞれのフラグが立ちます。

    ### 除外設定について
    
    「除外設定」では、特定の**差異ペア**を検出対象から除外できます。
    - 各行に「原語,訳語」の形式で入力します（例: `CPUs,CPU`）。
    - この設定は、検出された個々の差異ペア（例: `CPUs/CPU`）に適用されます。設定に一致したペアは、分析結果に表示されなくなります。
    - **以前のバージョンとの違い**: この除外設定はセグメント全体ではなく、個別の単語ペアにのみ影響します。そのため、セグメント内に除外したい差異と報告してほしい差異が混在していても、正しく処理されます。
    - 正規表現を使用する場合は、パターンの前に `r:` を付けてください（例: `r:[A-Z]+s,r:[A-Z]+`）。
    
    ### 英単語の抽出ルール
    - アルファベットとアンダーバーが2文字以上連続するものを英単語として抽出します。
    """)
