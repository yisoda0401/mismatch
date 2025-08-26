import streamlit as st
import xml.etree.ElementTree as ET
import re
import pandas as pd
import io
import html

# XML名前空間を登録
ET.register_namespace('xml', 'http://www.w3.org/XML/1998/namespace')

st.set_page_config(page_title="TMX分析ツール", layout="wide")
st.title("TMX分析ツール")
st.subheader("日本語訳に含まれる英単語が英語原文に存在するか確認・分析")

uploaded_file = st.file_uploader("TMXファイルをアップロード", type=["tmx"])

# --- UIの変更箇所 ---
# 除外設定のUIを定義
with st.expander("除外設定", expanded=False):
    
    default_exclusion_pairs = """r:[A-Z][A-Z]+s,r:[A-Z][A-Z]+
bean,Bean
cookie,Cookie
egress,Egress
ingress,Ingress
playbook,Playbook
pod,Pod
web,Web
personal access token,Personal Access Token
website,Web サイト
websites,Web サイト
vCPU,仮想 CPU
VIP,仮想 IP
manual page,man ページ"""
    
    exclusion_pairs_text = st.text_area(
        "除外ペア (各行に「原語,訳語」の形式で入力)",
        value=default_exclusion_pairs,
        height=150,
        help="各行に「原語,訳語」の形式で入力。大文字小文字は区別されます。詳細は「使い方」を参照。"
    )
    
    st.markdown("---") # 区切り線

    default_not_in_source_exclusions = """Red Hat
Wi-Fi"""

    not_in_source_exclusions_text = st.text_area(
        "「原文にない単語」から除外するリスト（1行に1つ入力）",
        value=default_not_in_source_exclusions,
        height=100,
        help="ここに入力された単語やフレーズは、「原文にない単語」として検出されなくなります。"
    )
    # --- UIの変更ここまで ---

    # 除外ペアの解析
    exclusion_pairs = []
    if exclusion_pairs_text:
        for line in exclusion_pairs_text.strip().split('\n'):
            if line and ',' in line:
                source, target = line.split(',', 1)
                exclusion_pairs.append((source.strip(), target.strip()))

    # 「原文にない単語」の除外リストの解析
    not_in_source_exclusions = set()
    if not_in_source_exclusions_text:
        for line in not_in_source_exclusions_text.strip().split('\n'):
            if line.strip():
                not_in_source_exclusions.add(line.strip())

def extract_english_words(text):
    """英単語を抽出（アルファベットとアンダーバーが2文字以上連続するもの）"""
    words = re.findall(r'\b[a-zA-Z_]{2,}\b', text)
    return words

def extract_hyphenated_phrases(text):
    """ハイフンが2つ以上含まれるフレーズを抽出"""
    return re.findall(r'\b[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+){2,}\b', text)

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
        if ' ' in source_rule or ' ' in target_rule:
            continue

        source_is_regex = source_rule.startswith('r:')
        target_is_regex = target_rule.startswith('r:')
        
        source_pattern = source_rule[2:] if source_is_regex else re.escape(source_rule)
        target_pattern = target_rule[2:] if target_is_regex else re.escape(target_rule)
        
        try:
            source_match = bool(re.fullmatch(source_pattern, source_word))
            target_match = bool(re.fullmatch(target_pattern, target_word))
            
            if source_match and target_match:
                return True
        except re.error:
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


# --- 分析ロジックの変更箇所 ---
def analyze_tmx(file_content, exclusion_pairs, not_in_source_exclusions):
    try:
        tree = ET.parse(io.BytesIO(file_content))
        root = tree.getroot()
        
        namespaces = dict([node for _, node in ET.iterparse(io.BytesIO(file_content), events=['start-ns'])])
        if not namespaces:
            namespaces['xml'] = 'http://www.w3.org/XML/1998/namespace'
        
        results = []
        
        phrase_rules = [p for p in exclusion_pairs if ' ' in p[0] or ' ' in p[1]]
        word_rules = [p for p in exclusion_pairs if ' ' not in p[0] and ' ' not in p[1]]

        # 除外リストを単語とフレーズに分割
        not_in_source_exclusion_words = {item for item in not_in_source_exclusions if ' ' not in item}
        not_in_source_exclusion_phrases = {item for item in not_in_source_exclusions if ' ' in item}

        tus = root.findall(".//tu") or root.findall(".//{*}tu")
        
        for idx, tu in enumerate(tus, 1):
            en_text_orig = ""
            ja_text_orig = ""
            
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
                    en_text_orig = text_content
                elif lang == "ja" or lang == "ja-jp":
                    ja_text_orig = text_content
            
            if en_text_orig and ja_text_orig:
                en_text_analyzable = en_text_orig
                ja_text_analyzable = ja_text_orig

                for src_phrase, tgt_phrase in phrase_rules:
                    if src_phrase.startswith('r:') or tgt_phrase.startswith('r:'):
                        continue
                    if src_phrase in en_text_analyzable and tgt_phrase in ja_text_analyzable:
                        en_text_analyzable = en_text_analyzable.replace(src_phrase, '')
                        ja_text_analyzable = ja_text_analyzable.replace(tgt_phrase, '')
                
                en_hyphen_phrases = set(extract_hyphenated_phrases(en_text_analyzable))
                ja_hyphen_phrases = set(extract_hyphenated_phrases(ja_text_analyzable))
                hyphen_diffs_words = [p for p in ja_hyphen_phrases if p not in en_hyphen_phrases]

                for phrase in en_hyphen_phrases:
                    en_text_analyzable = en_text_analyzable.replace(phrase, '')
                for phrase in ja_hyphen_phrases:
                    ja_text_analyzable = ja_text_analyzable.replace(phrase, '')

                en_words_case_sensitive = extract_english_words(en_text_analyzable)
                en_words_set_original = set(en_words_case_sensitive)
                en_words_dict_case_sensitive = {word: word for word in en_words_case_sensitive}
                en_words_dict_case_insensitive = {word.lower(): word for word in en_words_case_sensitive}
                ja_eng_words = extract_english_words(ja_text_analyzable)
                
                potential_words_not_in_source = []
                potential_case_diffs = []
                potential_sp_diffs = []
                potential_underscore_diffs = []

                for ja_word in ja_eng_words:
                    if '_' in ja_word:
                        if ja_word not in en_words_set_original:
                            potential_underscore_diffs.append(("-", ja_word))
                        continue

                    word_lower = ja_word.lower()

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
                
                # --- ここからが新しいフィルタリングロジック ---
                final_words_not_in_source_list = []
                # 訳文中に実際に存在する除外フレーズと、その構成単語のセットを作成
                active_exclusion_phrases_words = {}
                for phrase in not_in_source_exclusion_phrases:
                    if phrase in ja_text_orig:
                        active_exclusion_phrases_words[phrase] = set(extract_english_words(phrase))

                for word in potential_words_not_in_source:
                    is_excluded = False
                    # 1. 単語そのものが除外対象かチェック
                    if word in not_in_source_exclusion_words:
                        is_excluded = True
                    
                    # 2. 単語が除外フレーズの一部かチェック
                    if not is_excluded:
                        for phrase, words_in_phrase in active_exclusion_phrases_words.items():
                            if word in words_in_phrase:
                                is_excluded = True
                                break
                    
                    if not is_excluded:
                        final_words_not_in_source_list.append(word)
                # --- フィルタリングロジックここまで ---

                final_case_diffs_pairs = [(s, t) for s, t in potential_case_diffs if not is_pair_excluded(s, t, word_rules)]
                final_sp_diffs_pairs = list(set([(s, t) for s, t in potential_sp_diffs if not is_pair_excluded(s, t, word_rules)]))
                final_underscore_diffs_pairs = [(s, t) for s, t in potential_underscore_diffs if not is_pair_excluded(s, t, word_rules)]
                
                results.append({
                    "ID": idx,
                    "英語原文": en_text_orig,
                    "日本語訳": ja_text_orig,
                    "大/小文字違い": ", ".join([f"{s}/{t}" for s, t in final_case_diffs_pairs]) or "なし",
                    "単複の違い": ", ".join([f"{s}/{t}" for s, t in final_sp_diffs_pairs]) or "なし", 
                    "原文にない単語": ", ".join([f"-/{w}" for w in final_words_not_in_source_list]) or "なし",
                    "アンダーバー連結語": ", ".join([f"{s}/{t}" for s, t in final_underscore_diffs_pairs]) or "なし",
                    "ハイフン連結語": ", ".join([f"-/{p}" for p in hyphen_diffs_words]) or "なし",
                    "要確認(大/小文字違い)": len(final_case_diffs_pairs) > 0,
                    "要確認(単複の違い)": len(final_sp_diffs_pairs) > 0,
                    "要確認(原文にない単語)": len(final_words_not_in_source_list) > 0,
                    "要確認(アンダーバー連結語)": len(final_underscore_diffs_pairs) > 0,
                    "要確認(ハイフン連結語)": len(hyphen_diffs_words) > 0,
                    "case_diffs_words": final_case_diffs_pairs,
                    "sp_diffs_words": final_sp_diffs_pairs,
                    "not_in_source_words": final_words_not_in_source_list,
                    "underscore_diffs_words": final_underscore_diffs_pairs,
                    "hyphen_diffs_words": hyphen_diffs_words
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

def highlight_text(text, diff_data):
    """テキスト内の指定された単語をハイライトするHTMLを生成する"""
    highlighted_text = html.escape(text)

    for word in sorted(diff_data.get('hyphen', []), key=len, reverse=True):
        highlighted_text = re.sub(r'\b' + re.escape(html.escape(word)) + r'\b', f'<span class="highlight-hyphen">{html.escape(word)}</span>', highlighted_text)

    for _, word in sorted(diff_data.get('underscore', []), key=lambda x: len(x[1]), reverse=True):
        highlighted_text = re.sub(r'\b' + re.escape(html.escape(word)) + r'\b', f'<span class="highlight-underscore">{html.escape(word)}</span>', highlighted_text)

    for word in sorted(diff_data.get('not_in_source', []), key=len, reverse=True):
        highlighted_text = re.sub(r'\b' + re.escape(html.escape(word)) + r'\b', f'<span class="highlight-not-in-source">{html.escape(word)}</span>', highlighted_text)
    
    for en_word, ja_word in sorted(diff_data.get('sp', []), key=lambda x: len(x[1]), reverse=True):
        highlighted_text = re.sub(r'\b' + re.escape(html.escape(ja_word)) + r'\b', f'<span class="highlight-sp">{html.escape(ja_word)}</span>', highlighted_text)
    for en_word, ja_word in sorted(diff_data.get('sp', []), key=lambda x: len(x[0]), reverse=True):
        highlighted_text = re.sub(r'\b' + re.escape(html.escape(en_word)) + r'\b', f'<span class="highlight-sp">{html.escape(en_word)}</span>', highlighted_text)

    for en_word, ja_word in sorted(diff_data.get('case', []), key=lambda x: len(x[1]), reverse=True):
        highlighted_text = re.sub(r'\b' + re.escape(html.escape(ja_word)) + r'\b', f'<span class="highlight-case">{html.escape(ja_word)}</span>', highlighted_text)
    for en_word, ja_word in sorted(diff_data.get('case', []), key=lambda x: len(x[0]), reverse=True):
        highlighted_text = re.sub(r'\b' + re.escape(html.escape(en_word)) + r'\b', f'<span class="highlight-case">{html.escape(en_word)}</span>', highlighted_text)

    return highlighted_text


if uploaded_file is not None:
    file_content = uploaded_file.read()
    
    with st.spinner("TMXファイルを分析中..."):
        # --- 関数呼び出しの変更箇所 ---
        df = analyze_tmx(file_content, exclusion_pairs, not_in_source_exclusions)
    
    if df is not None and not df.empty:
        st.metric("総セグメント数", f"{len(df)}")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1: 
            st.metric("要確認 (大/小文字違い)", f"{df['要確認(大/小文字違い)'].sum()}")
        with col2:
            st.metric("要確認 (単複の違い)", f"{df['要確認(単複の違い)'].sum()}")
        with col3:
            st.metric("要確認 (原文にない単語)", f"{df['要確認(原文にない単語)'].sum()}")
        with col4:
            st.metric("要確認 (アンダーバー連結語)", f"{df['要確認(アンダーバー連結語)'].sum()}")
        with col5:
            st.metric("要確認 (ハイフン連結語)", f"{df['要確認(ハイフン連結語)'].sum()}")
        
        st.subheader("分析結果")
        
        filter_option = st.radio(
            "表示オプション:",
            ["すべて表示", "大/小文字違い", "単複の違い", "原文にない単語", "アンダーバー連結語", "ハイフン連結語", "いずれかの方法で要確認"],
            index=6, horizontal=True
        )
        
        if filter_option == "大/小文字違い":
            filtered_df = df[df["要確認(大/小文字違い)"] == True]
        elif filter_option == "単複の違い":
            filtered_df = df[df["要確認(単複の違い)"] == True]
        elif filter_option == "原文にない単語":
            filtered_df = df[df["要確認(原文にない単語)"] == True]
        elif filter_option == "アンダーバー連結語":
            filtered_df = df[df["要確認(アンダーバー連結語)"] == True]
        elif filter_option == "ハイフン連結語":
            filtered_df = df[df["要確認(ハイフン連結語)"] == True]
        elif filter_option == "いずれかの方法で要確認":
            filtered_df = df[
                             (df["要確認(原文にない単語)"] == True) | (df["要確認(大/小文字違い)"] == True) |
                             (df["要確認(単複の違い)"] == True) | (df["要確認(アンダーバー連結語)"] == True) |
                             (df["要確認(ハイフン連結語)"] == True)
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
        elif filter_option == "アンダーバー連結語":
            columns_to_display = base_columns + ["アンダーバー連結語"]
        elif filter_option == "ハイフン連結語":
            columns_to_display = base_columns + ["ハイフン連結語"]
        else:
            columns_to_display = base_columns + ["大/小文字違い", "単複の違い", "原文にない単語", "アンダーバー連結語", "ハイフン連結語"]
            
        if not filtered_df.empty: 
            filtered_df_display = filtered_df[columns_to_display].copy()
        else: 
            filtered_df_display = pd.DataFrame(columns=columns_to_display)

        html_str = """
        <style>
            .styled-table { border-collapse: collapse; width: 100%; font-size: 14px; text-align: left; }
            .styled-table th { background-color: #f2f2f2; color: #333; font-weight: bold; padding: 10px 8px; border: 1px solid #ddd; }
            .styled-table td { padding: 8px; border: 1px solid #ddd; word-wrap: break-word; max-width: 350px; vertical-align: top; }
            .styled-table tr:nth-child(even) { background-color: #f9f9f9; }
            .styled-table tr:nth-child(odd) { background-color: #ffffff; }
            .styled-table tr:hover { background-color: #e6f7ff; }
            .index-column { width: 50px; text-align: center; font-weight: bold; }
            .highlight-case { background-color: #FFDDC1; font-weight: bold; padding: 1px 2px; border-radius: 3px; }
            .highlight-sp { background-color: #C1FFD7; font-weight: bold; padding: 1px 2px; border-radius: 3px; }
            .highlight-not-in-source { background-color: #FFC1C1; font-weight: bold; padding: 1px 2px; border-radius: 3px; }
            .highlight-underscore { background-color: #C1D4FF; font-weight: bold; padding: 1px 2px; border-radius: 3px; }
            .highlight-hyphen { background-color: #F3C1FF; font-weight: bold; padding: 1px 2px; border-radius: 3px; }
        </style>
        <table class="styled-table"><thead><tr>
        """
        for col in filtered_df_display.columns:
            html_str += f"<th class='{'index-column' if col == 'ID' else ''}'>{col}</th>"
        html_str += "</tr></thead><tbody>"

        if not filtered_df.empty:
            for _, row in filtered_df.iterrows():
                html_str += "<tr>"
                for col_name in filtered_df_display.columns:
                    cell_value = row[col_name]
                    cell_class = "index-column" if col_name == "ID" else ""
                    
                    if col_name == "英語原文":
                        diff_data = {
                            'case': row['case_diffs_words'],
                            'sp': row['sp_diffs_words']
                        }
                        display_text = highlight_text(cell_value, diff_data)
                        html_str += f"<td class='{cell_class.strip()}'>{display_text}</td>"
                    elif col_name == "日本語訳":
                        diff_data = {
                            'case': row['case_diffs_words'],
                            'sp': row['sp_diffs_words'],
                            'not_in_source': row['not_in_source_words'],
                            'underscore': row['underscore_diffs_words'],
                            'hyphen': row['hyphen_diffs_words']
                        }
                        display_text = highlight_text(cell_value, diff_data)
                        html_str += f"<td class='{cell_class.strip()}'>{display_text}</td>"
                    elif cell_value == "なし" and col_name in ["原文にない単語", "大/小文字違い", "単複の違い", "アンダーバー連結語", "ハイフン連結語"]: 
                        html_str += f"<td class='{cell_class.strip()}' style='color: green;'>{cell_value}</td>"
                    else:
                        html_str += f"<td class='{cell_class.strip()}'>{html.escape(str(cell_value))}</td>"
                html_str += "</tr>"
        else:
             html_str += f"<tr><td colspan='{len(columns_to_display)}' style='text-align:center;'>該当するデータがありません。</td></tr>"
        html_str += "</tbody></table>"
        st.write(html_str, unsafe_allow_html=True)
        
        if not filtered_df.empty:
            csv_df = filtered_df[columns_to_display].copy()
            csv = csv_df.to_csv(index=False).encode('utf-8-sig')
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

# --- 「使い方」の更新箇所 ---
with st.expander("使い方"):
    st.markdown("""
    ### このアプリケーションの使い方
    
    1. 上部の「Browse files」ボタンをクリックしてTMXファイルをアップロードします。
    2. 必要に応じて「除外設定」で除外するペアや単語を設定します。
    3. アプリが自動的にファイルを分析し、結果を表示します。
    4. **分析結果の概要**: 各確認項目について、要確認と判断されたセグメント数が表示されます。
    5. **分析結果テーブル**:
        - **ID**: 翻訳ユニットの通し番号。
        - **英語原文 / 日本語訳**: TMXファイル内の原文と訳文。**差異が検出された単語は色付きでハイライトされます。**
        - **大/小文字違い**: 日本語訳中の英単語が、大文字・小文字を区別すると英語原文に存在しないが、無視すると存在する場合に、そのペアをリストアップします (例: `Pod/pod`)。
        - **単複の違い**: 日本語訳中の英単語が、英語原文の単語と単数形・複数形のみ異なる場合に、そのペアをリストアップします (例: `book/books`)。
        - **原文にない単語**: 日本語訳中の英単語が、大文字・小文字を無視しても英語原文に存在しない場合に、`- / 訳文の単語` の形式でリストアップします (例: `-/word`)。
        - **アンダーバー連結語**: 訳文に含まれるアンダースコアを含む単語が、原文に存在しない場合に `- / 訳文の単語` 形式でリストアップします (例: `-/new_var`)。
        - **ハイフン連結語**: 訳文に含まれるハイフンが2つ以上のフレーズ（例: `insights-runtime-extractor`）が、原文に存在しない場合に `- / 訳文のフレーズ` 形式でリストアップします。
    6. **表示オプション**: テーブルに表示するセグメントをフィルタリングできます。
    7. 分析結果はCSV形式でダウンロードできます。
    
    ### 「要確認」の判断基準
    - 各「要確認」列にペアが1つ以上リストアップされた場合に、それぞれのフラグが立ちます。

    ### 除外設定について
    
    「除外設定」では、特定の差異を検出対象から除外できます。設定項目は2種類あります。
    
    #### 1. 除外ペア
    原文と訳文のペアを指定して除外します。この設定はさらに2段階で適用されます。
    - **フレーズの除外**: 設定にスペースを含むルール（例: `personal access token,Personal Access Token`）は「フレーズ」として扱われ、分析の最初に、原文と訳文の両方に一致するフレーズが後続の単語分析の対象から除外されます。(注: フレーズの除外に正規表現は使用できません)
    - **単語の除外**: スペースを含まないルール（例: `CPUs,CPU`）は、検出された個々の単語ペアに適用され、一致したものが結果から除外されます。単語の除外では正規表現が使用できます（例: `r:[A-Z]+s,r:[A-Z]+`）。
    
    #### 2. 「原文にない単語」から除外するリスト
    **訳文のみを対象**として、指定した単語やフレーズを「原文にない単語」の検出結果から除外します。
    - **目的**: 訳注や製品の固有名詞など、意図的に訳文に追加した英単語が警告として表示されないようにします。
    - **使い方**: 1行に1つ、除外したい単語またはフレーズを入力します（例: `ABC Company`）。
    - **動作**: ここに `ABC Company` と入力すると、訳文に `ABC Company` が含まれていた場合、`ABC` と `Company` は「原文にない単語」として検出されなくなります。
    
    ### 英単語の抽出ルール
    - **通常**: アルファベットとアンダーバーが2文字以上連続するものを英単語として抽出します。
    - **ハイフン連結語**: 英数字がハイフンで3つ以上連結されたもの（例: `word-word-word`）を個別のカテゴリとして抽出し、分析します。
    """)
