# translate-toolkitライブラリが必要です。
# pip install translate-toolkit
import streamlit as st
import re
import pandas as pd
import io
import html
from translate.storage import tmx

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
"""

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


def analyze_tmx(file_content, exclusion_pairs, not_in_source_exclusions):
    """
    TMXファイルを解析する関数。
    """
    try:
        tmx_file_obj = io.BytesIO(file_content)
        tmx_file = tmx.tmxfile(tmx_file_obj)
        
        results = []
        
        phrase_rules = [p for p in exclusion_pairs if ' ' in p[0] or ' ' in p[1]]
        word_rules = [p for p in exclusion_pairs if ' ' not in p[0] and ' ' not in p[1]]

        not_in_source_exclusion_words = {item for item in not_in_source_exclusions if ' ' not in item}
        not_in_source_exclusion_phrases = {item for item in not_in_source_exclusions if ' ' in item}

        for idx, unit in enumerate(tmx_file.units, 1):
            en_text_orig = unit.source
            ja_text_orig = unit.target
            
            if en_text_orig and ja_text_orig:
                en_tags = re.findall(r'(<[^>]+>)', en_text_orig)
                ja_tags = re.findall(r'(<[^>]+>)', ja_text_orig)
                
                # --- ★変更点: タグのリストをソートしてから比較し、順序の違いを無視 ---
                tag_mismatch = sorted(en_tags) != sorted(ja_tags)
                tag_mismatch_details = f"原文: {en_tags} / 訳文: {ja_tags}" if tag_mismatch else "なし"

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
                
                final_words_not_in_source_list = []
                active_exclusion_phrases_words = {}
                for phrase in not_in_source_exclusion_phrases:
                    if phrase in ja_text_orig:
                        active_exclusion_phrases_words[phrase] = set(extract_english_words(phrase))

                for word in potential_words_not_in_source:
                    is_excluded = False
                    if word in not_in_source_exclusion_words:
                        is_excluded = True
                    
                    if not is_excluded:
                        for phrase, words_in_phrase in active_exclusion_phrases_words.items():
                            if word in words_in_phrase:
                                is_excluded = True
                                break
                    
                    if not is_excluded:
                        final_words_not_in_source_list.append(word)

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
                    "タグの不一致": tag_mismatch_details,
                    "要確認(大/小文字違い)": len(final_case_diffs_pairs) > 0,
                    "要確認(単複の違い)": len(final_sp_diffs_pairs) > 0,
                    "要確認(原文にない単語)": len(final_words_not_in_source_list) > 0,
                    "要確認(アンダーバー連結語)": len(final_underscore_diffs_pairs) > 0,
                    "要確認(ハイフン連結語)": len(hyphen_diffs_words) > 0,
                    "要確認(タグの不一致)": tag_mismatch,
                    "case_diffs_words": final_case_diffs_pairs,
                    "sp_diffs_words": final_sp_diffs_pairs,
                    "not_in_source_words": final_words_not_in_source_list,
                    "underscore_diffs_words": final_underscore_diffs_pairs,
                    "hyphen_diffs_words": hyphen_diffs_words
                })
        
        if not results:
            st.warning("翻訳ペアが見つかりませんでした。TMXファイルの構造を確認してください。")
            with st.expander("TMXファイル構造（デバッグ）"):
                tmx_string_for_debug = file_content.decode('utf-8', errors='ignore')
                st.code(tmx_string_for_debug[:5000] + ("..." if len(tmx_string_for_debug) > 5000 else ""), language="xml")
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

def combine_other_issues(row):
    """「その他」列に表示するためのHTML文字列を生成する"""
    parts = []
    if row['アンダーバー連結語'] != 'なし':
        parts.append(f"<b>アンダーバー連結語:</b> {html.escape(row['アンダーバー連結語'])}")
    if row['ハイフン連結語'] != 'なし':
        parts.append(f"<b>ハイフン連結語:</b> {html.escape(row['ハイフン連結語'])}")
    if row['タグの不一致'] != 'なし':
        parts.append(f"<b>タグの不一致:</b> {html.escape(row['タグの不一致'])}")
    
    if not parts:
        return 'なし'
    return '<br>'.join(parts)

if uploaded_file is not None:
    file_content = uploaded_file.read()
    
    with st.spinner("TMXファイルを分析中..."):
        df = analyze_tmx(file_content, exclusion_pairs, not_in_source_exclusions)
    
    if df is not None and not df.empty:
        st.metric("総セグメント数", f"{len(df)}")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1: 
            st.metric("大/小文字違い", f"{df['要確認(大/小文字違い)'].sum()}")
        with col2:
            st.metric("単複の違い", f"{df['要確認(単複の違い)'].sum()}")
        with col3:
            st.metric("原文にない単語", f"{df['要確認(原文にない単語)'].sum()}")
        with col4:
            other_issues_count = df[
                (df['要確認(アンダーバー連結語)']) |
                (df['要確認(ハイフン連結語)']) |
                (df['要確認(タグの不一致)'])
            ].shape[0]
            st.metric("その他", f"{other_issues_count}")
        
        st.subheader("分析結果")
        
        filter_option = st.radio(
            "表示オプション:",
            ["すべて表示", "大/小文字違い", "単複の違い", "原文にない単語", "その他", "いずれかの方法で要確認"],
            index=5, horizontal=True
        )
        
        df['その他'] = df.apply(combine_other_issues, axis=1)
        df['要確認(その他)'] = (df['要確認(アンダーバー連結語)']) | (df['要確認(ハイフン連結語)']) | (df['要確認(タグの不一致)'])

        if filter_option == "大/小文字違い":
            filtered_df = df[df["要確認(大/小文字違い)"] == True]
        elif filter_option == "単複の違い":
            filtered_df = df[df["要確認(単複の違い)"] == True]
        elif filter_option == "原文にない単語":
            filtered_df = df[df["要確認(原文にない単語)"] == True]
        elif filter_option == "その他":
            filtered_df = df[df["要確認(その他)"] == True]
        elif filter_option == "いずれかの方法で要確認":
            filtered_df = df[
                             (df["要確認(原文にない単語)"] == True) | (df["要確認(大/小文字違い)"] == True) |
                             (df["要確認(単複の違い)"] == True) | (df["要確認(その他)"] == True)
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
        elif filter_option == "その他":
            columns_to_display = base_columns + ["その他"]
        else:
            columns_to_display = base_columns + ["大/小文字違い", "単複の違い", "原文にない単語", "その他"]
            
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
                            'case': df.loc[row.name]['case_diffs_words'],
                            'sp': df.loc[row.name]['sp_diffs_words']
                        }
                        display_text = highlight_text(str(cell_value), diff_data)
                        html_str += f"<td class='{cell_class.strip()}'>{display_text}</td>"
                    elif col_name == "日本語訳":
                        original_row = df.loc[row.name]
                        diff_data = {
                            'case': original_row['case_diffs_words'],
                            'sp': original_row['sp_diffs_words'],
                            'not_in_source': original_row['not_in_source_words'],
                            'underscore': original_row['underscore_diffs_words'],
                            'hyphen': original_row['hyphen_diffs_words']
                        }
                        display_text = highlight_text(str(cell_value), diff_data)
                        html_str += f"<td class='{cell_class.strip()}'>{display_text}</td>"
                    elif col_name == "その他":
                        html_str += f"<td class='{cell_class.strip()}'>{cell_value}</td>"
                    elif cell_value == "なし" and col_name in ["原文にない単語", "大/小文字違い", "単複の違い"]: 
                        html_str += f"<td class='{cell_class.strip()}' style='color: green;'>{cell_value}</td>"
                    else:
                        html_str += f"<td class='{cell_class.strip()}'>{html.escape(str(cell_value))}</td>"
                html_str += "</tr>"
        else:
             html_str += f"<tr><td colspan='{len(columns_to_display)}' style='text-align:center;'>該当するデータがありません。</td></tr>"
        html_str += "</tbody></table>"
        st.write(html_str, unsafe_allow_html=True)
        
        if not filtered_df.empty:
            def format_other_for_csv(row):
                parts = []
                if row['アンダーバー連結語'] != 'なし':
                    parts.append(f"アンダーバー連結語: {row['アンダーバー連結語']}")
                if row['ハイフン連結語'] != 'なし':
                    parts.append(f"ハイフン連結語: {row['ハイフン連結語']}")
                if row['タグの不一致'] != 'なし':
                    parts.append(f"タグの不一致: {row['タグの不一致']}")
                return " | ".join(parts) if parts else "なし"
            
            csv_df = filtered_df[columns_to_display].copy()
            if 'その他' in csv_df.columns:
                 csv_df['その他'] = filtered_df.apply(format_other_for_csv, axis=1)

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
        - **その他 (新設)**: 以下の3つの項目をまとめて表示します。
            - **アンダーバー連結語**: 訳文に含まれるアンダースコアを含む単語が、原文に存在しない場合に表示します。
            - **ハイフン連結語**: 訳文に含まれるハイフンが2つ以上のフレーズが、原文に存在しない場合に表示します。
            - **タグの不一致**: 原文と訳文で、`<ph>`や`<strong>`のようなインラインタグの種類や数が異なる場合に、その詳細を表示します。**(タグの順序の違いは無視されます)**。
    6. **表示オプション**: テーブルに表示するセグメントをフィルタリングできます。
    7. 分析結果はCSV形式でダウンロードできます。
    
    ### 「要確認」の判断基準
    - 各「要確認」列にペアが1つ以上リストアップされたり、不一致が検出された場合に、それぞれのフラグが立ちます。

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
    - **通常**: アルファベットとアンダーバーが2文字以上連続するものを英単語として抽出します。インラインタグは無視されます。
    - **ハイフン連結語**: 英数字がハイフンで3つ以上連結されたもの（例: `word-word-word`）を個別のカテゴリとして抽出し、分析します。
    """)
