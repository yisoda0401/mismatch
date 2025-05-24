import streamlit as st
import xml.etree.ElementTree as ET
import re
import pandas as pd
import io

# XML名前空間を登録
ET.register_namespace('xml', 'http://www.w3.org/XML/1998/namespace')

st.set_page_config(page_title="TMX分析ツール", layout="wide")
st.title("TMX分析ツール")
st.subheader("日本語訳に含まれる英単語が英語原文に存在するか確認・分析") # サブヘッダーを少し汎用的に

uploaded_file = st.file_uploader("TMXファイルをアップロード", type=["tmx"])

# 除外ペアの入力エリア
with st.expander("除外設定", expanded=False):
    
    # デフォルトの除外ペア設定に正規表現の例を追加
    default_exclusion_pairs = """r:\\b\\w+[^s]s\\b,r:\\b\\w+\\b
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
    # 英単語を抽出（アルファベットが2文字以上連続するもの）
    # 大文字小文字を区別して抽出
    words = re.findall(r'\b[a-zA-Z]{2,}\b', text)
    return words  # 大文字小文字を維持

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

def should_exclude(en_text, ja_text, exclusion_pairs):
    """指定された除外ペアに基づいて、このセグメントを除外すべきかを判断"""
    for source, target in exclusion_pairs:
        # 正規表現パターンかどうかを確認
        source_is_regex = source.startswith('r:')
        target_is_regex = target.startswith('r:')
        
        # 正規表現パターンの場合は先頭の 'r:' を削除
        source_pattern = source[2:] if source_is_regex else source
        target_pattern = target[2:] if target_is_regex else target
        
        # 条件チェック
        source_match = False
        target_match = False
        
        try:
            if source_is_regex:
                # 正規表現マッチングを実行
                source_match = bool(re.search(source_pattern, en_text))
            else:
                # 通常の文字列検索
                source_match = source in en_text
                
            if target_is_regex:
                # 正規表現マッチングを実行
                target_match = bool(re.search(target_pattern, ja_text))
            else:
                # 通常の文字列検索
                target_match = target in ja_text
                
            # 両方マッチした場合は除外
            if source_match and target_match:
                return True
        except re.error as e:
            # 正規表現エラーを処理（ログに記録するなど）
            st.warning(f"正規表現エラー: {str(e)} - パターン: '{source_pattern}' または '{target_pattern}'")
            continue
    
    return False

def are_singular_plural_pair(word1, word2):
    """
    2つの単語が単数形と複数形のペアであるか（大文字小文字を無視して）判定する。
    word1 と word2 のどちらが単数形でも複数形でも対応。
    """
    w1_lower = word1.lower()
    w2_lower = word2.lower()

    if w1_lower == w2_lower: # 全く同じ単語はペアとしない
        return False

    # 不規則変化の基本的な対応 (辞書は必要に応じて拡張)
    irregular_map = {
        "child": "children", "man": "men", "woman": "women", "tooth": "teeth",
        "foot": "feet", "mouse": "mice", "goose": "geese", "ox": "oxen",
        "person": "people", "die": "dice", "corpus": "corpora", "focus": "foci",
        "datum": "data", "medium": "media", "analysis": "analyses", "basis": "bases",
        "criterion": "criteria", "phenomenon": "phenomena", "index": "indices", 
        "thesis": "theses", "radius": "radii", "formula": "formulae", # "formulas" もあり得る
        "shelf": "shelves", "leaf": "leaves", "knife": "knives", "life": "lives", "wolf": "wolves",
        "cactus": "cacti", "syllabus": "syllabi" 
    }
    # 辞書の双方向チェック
    if irregular_map.get(w1_lower) == w2_lower or irregular_map.get(w2_lower) == w1_lower:
        return True

    # 規則的な変化のチェック (w1が単数形、w2が複数形)
    if w1_lower + 's' == w2_lower: return True
    # -y -> -ies
    if w1_lower.endswith('y') and len(w1_lower) > 1 and w1_lower[-2].lower() not in 'aeiou' and w1_lower[:-1] + 'ies' == w2_lower: return True
    # -s, -x, -z, -ch, -sh, -o -> -es
    if any(w1_lower.endswith(s) for s in ['s', 'x', 'z', 'ch', 'sh', 'o']) and w1_lower + 'es' == w2_lower: return True
    # -f (but not -ff) -> -ves
    if (w1_lower.endswith('f') and not w1_lower.endswith('ff')) and w1_lower[:-1] + 'ves' == w2_lower: return True 
    # -fe -> -ves
    if w1_lower.endswith('fe') and w1_lower[:-2] + 'ves' == w2_lower: return True

    # 規則的な変化のチェック (w2が単数形、w1が複数形)
    if w2_lower + 's' == w1_lower: return True
    # -y -> -ies
    if w2_lower.endswith('y') and len(w2_lower) > 1 and w2_lower[-2].lower() not in 'aeiou' and w2_lower[:-1] + 'ies' == w1_lower: return True
    # -s, -x, -z, -ch, -sh, -o -> -es
    if any(w2_lower.endswith(s) for s in ['s', 'x', 'z', 'ch', 'sh', 'o']) and w2_lower + 'es' == w1_lower: return True
    # -f (but not -ff) -> -ves
    if (w2_lower.endswith('f') and not w2_lower.endswith('ff')) and w2_lower[:-1] + 'ves' == w1_lower: return True
    # -fe -> -ves
    if w2_lower.endswith('fe') and w2_lower[:-2] + 'ves' == w1_lower: return True
    
    return False


def analyze_tmx(file_content, exclusion_pairs):
    try:
        # XMLパーサーでファイルを解析
        tree = ET.parse(io.BytesIO(file_content))
        root = tree.getroot()
        
        # 名前空間を取得
        namespaces = dict([node for _, node in ET.iterparse(io.BytesIO(file_content), events=['start-ns'])])
        if not namespaces:
            # 名前空間がない場合はデフォルト設定
            namespaces['xml'] = 'http://www.w3.org/XML/1998/namespace'
        
        results = []
        excluded_count = 0
        
        # TMXファイルの構造に基づいて翻訳ユニットを探す
        tus = root.findall(".//tu") or root.findall(".//{*}tu")
        
        for idx, tu in enumerate(tus, 1):  # 1から始まるインデックスを付与
            en_text = ""
            ja_text = ""
            
            # 全てのsegタグを検索
            segs = tu.findall(".//seg") or tu.findall(".//{*}seg")
            
            for seg in segs:
                # tuv要素（親要素）を取得
                parent = None
                for parent_elem in tu:
                    if seg in parent_elem.iter():
                        parent = parent_elem
                        break
                
                # xml:lang属性を確認
                lang = None
                
                # 直接属性を確認
                if parent is not None:
                    # 通常の属性名でチェック
                    lang = parent.get("xml:lang") or parent.get("{http://www.w3.org/XML/1998/namespace}lang")
                    
                    # 属性が見つからない場合は全属性をチェック
                    if lang is None:
                        for attr_name, attr_value in parent.attrib.items():
                            if attr_name.endswith('lang'):
                                lang = attr_value
                                break
                
                # segタグ内のすべてのテキストを取得（子タグも含む）
                text_content = get_full_text_content(seg)
                
                # 言語に基づいて適切な変数に格納
                if lang == "en-us" or lang == "en":
                    en_text = text_content
                elif lang == "ja" or lang == "ja-jp":
                    ja_text = text_content
            
            if en_text and ja_text:  # 両方のテキストが存在する場合のみ処理
                # 除外条件をチェック
                if exclusion_pairs and should_exclude(en_text, ja_text, exclusion_pairs):
                    excluded_count += 1
                    continue  # このセグメントをスキップ
                
                # 英語セグメントから単語を抽出（大文字小文字を維持）
                en_words_case_sensitive = extract_english_words(en_text)
                en_words_set_original = set(en_words_case_sensitive) # 高速なルックアップ用
                
                # 大文字小文字を区別した辞書を作成（出現形を保持） - 「大/小文字違い」の検出に必要
                en_words_dict_case_sensitive = {}
                for word in en_words_case_sensitive:
                    en_words_dict_case_sensitive[word] = word
                
                # 日本語セグメントから英単語を抽出
                ja_eng_words = extract_english_words(ja_text)
                
                # 大文字小文字を区別しない分析
                # 小文字変換した辞書を作成
                en_words_dict_case_insensitive = {}
                for word in en_words_case_sensitive:
                    en_words_dict_case_insensitive[word.lower()] = word # 元の単語を保持
                
                missing_words_case_insensitive = []
                case_difference_words = []  # 大文字小文字だけが違う単語を格納
                singular_plural_differences = [] # 単複の違いを格納

                for ja_word in ja_eng_words:
                    word_lower = ja_word.lower()
                    
                    # 1. 大文字小文字無視で原文に存在するか (missing_words_case_insensitive)
                    if word_lower not in en_words_dict_case_insensitive:
                        missing_words_case_insensitive.append(ja_word)
                    # 2. 大文字小文字無視で存在する場合、大文字小文字区別で存在しないか (case_difference_words)
                    elif ja_word not in en_words_dict_case_sensitive:
                        # この時点で word_lower は en_words_dict_case_insensitive に存在する
                        # en_words_dict_case_insensitive[word_lower] は原文の単語 (大文字小文字維持)
                        # ja_word は訳文の単語 (大文字小文字維持)
                        case_difference_words.append(f"{en_words_dict_case_insensitive[word_lower]}/{ja_word}")
                    
                    # 3. 単複の違いのチェック (原文に完全一致せず、かつ大文字小文字違いでもない場合、またはそれらとは独立してチェック)
                    #    原文に完全一致する単語が訳文にある場合は、単複の違いとして検出すべきではない。
                    #    また、大文字小文字違いとして既に検出されている場合も、重複して単複の違いとしてリストアップする必要はないかもしれないが、
                    #    ここでは独立してチェックし、ユーザーが判断できるようにする。
                    #    test.py のロジック: ja_word が en_words_set_original (原文単語セット、大文字小文字区別) に完全一致しない場合に単複チェック
                    
                    is_exact_match_in_source = ja_word in en_words_set_original
                    
                    if not is_exact_match_in_source: # 完全一致しない場合のみ単複チェック
                        found_sp_pair = False
                        for en_word_orig_from_src in en_words_case_sensitive: # 原文の各単語と比較
                            if are_singular_plural_pair(ja_word, en_word_orig_from_src):
                                singular_plural_differences.append(f"{en_word_orig_from_src}/{ja_word}")
                                found_sp_pair = True
                                break # この ja_word に対する単複ペアが見つかった
                        # if found_sp_pair and ja_word in missing_words_case_insensitive:
                            # もし単複ペアが見つかり、かつ「大文字小文字無視」でも見つからないリストに入っていたら、
                            # それは純粋な単複違いの可能性が高いので、missing_words_case_insensitive から削除することも検討できる
                            # ただし、複雑になるため、一旦は各リストを独立して作成する
                
                results.append({
                    "ID": idx,
                    "英語原文": en_text,
                    "日本語訳": ja_text,
                    "日本語訳に含まれる英単語": ", ".join(ja_eng_words) if ja_eng_words else "なし",
                    "大/小文字無視": ", ".join(missing_words_case_insensitive) if missing_words_case_insensitive else "なし",
                    "大/小文字違い": ", ".join(case_difference_words) if case_difference_words else "なし",
                    "単複の違い": ", ".join(singular_plural_differences) if singular_plural_differences else "なし", # 新しい列
                    "要確認(大/小文字無視)": len(missing_words_case_insensitive) > 0,
                    "要確認(大/小文字違い)": len(case_difference_words) > 0,
                    "要確認(単複の違い)": len(singular_plural_differences) > 0 # 新しいフラグ
                })
        
        if excluded_count > 0:
            st.info(f"除外条件に一致したセグメント数: {excluded_count}")
        
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
        # 分析結果の概要
        case_difference_count = df["要確認(大/小文字違い)"].sum()
        case_insensitive_count = df["要確認(大/小文字無視)"].sum()
        singular_plural_count = df["要確認(単複の違い)"].sum() # 新しいメトリック
        
        col1, col2, col3 = st.columns(3) # 3列に変更
        with col1: 
            st.metric("要確認 (大/小文字違い)", f"{case_difference_count} / {len(df)}")
        with col2: 
            st.metric("要確認 (大/小文字無視)", f"{case_insensitive_count} / {len(df)}")
        with col3: # 新しいメトリック用
            st.metric("要確認 (単複の違い)", f"{singular_plural_count} / {len(df)}")
        
        st.subheader("分析結果")
        
        filter_option = st.radio(
            "表示オプション:",
            ["すべて表示", 
             "要確認のみ(大/小文字違い)",
             "要確認のみ(大/小文字無視)",
             "要確認のみ(単複の違い)", # 新しいオプション
             "いずれかの方法で要確認"],
            index=4,  # デフォルトを「いずれかの方法で要確認」に調整
            horizontal=True
        )
        
        if filter_option == "要確認のみ(大/小文字違い)":
            filtered_df = df[df["要確認(大/小文字違い)"] == True]
        elif filter_option == "要確認のみ(大/小文字無視)":
            filtered_df = df[df["要確認(大/小文字無視)"] == True]
        elif filter_option == "要確認のみ(単複の違い)": # 新しいフィルター条件
            filtered_df = df[df["要確認(単複の違い)"] == True]
        elif filter_option == "いずれかの方法で要確認":
            filtered_df = df[
                             (df["要確認(大/小文字無視)"] == True) | 
                             (df["要確認(大/小文字違い)"] == True) |
                             (df["要確認(単複の違い)"] == True) # 新しいフラグもチェック
                            ]
        else: # すべて表示
            filtered_df = df
        
        base_columns = ["ID", "英語原文", "日本語訳"]
        
        if filter_option == "要確認のみ(大/小文字違い)":
            columns_to_display = base_columns + ["大/小文字違い"]
        elif filter_option == "要確認のみ(大/小文字無視)":
            columns_to_display = base_columns + ["大/小文字無視"]
        elif filter_option == "要確認のみ(単複の違い)": # 新しいオプションの表示列
            columns_to_display = base_columns + ["単複の違い"]
        else: # すべて表示 または いずれかの方法で要確認
            columns_to_display = base_columns + ["大/小文字違い", "大/小文字無視", "単複の違い"] # 新しい列も追加
            
        if not filtered_df.empty: 
            filtered_df_display = filtered_df[columns_to_display].copy()
        else: 
            filtered_df_display = pd.DataFrame(columns=columns_to_display)

        html = """
        <style>
            .styled-table { border-collapse: collapse; width: 100%; font-size: 14px; text-align: left; }
            .styled-table th { background-color: #f2f2f2; color: #333; font-weight: bold; padding: 10px 8px; border: 1px solid #ddd; }
            .styled-table td { padding: 8px; border: 1px solid #ddd; word-wrap: break-word; max-width: 350px; } /* max-width調整 */
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
                    if cell_value == "なし" and col_name in ["大/小文字無視", "大/小文字違い", "単複の違い"]: 
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
        pass # エラーや翻訳ペアなしの場合は analyze_tmx 内でメッセージ表示
else:
    st.info("TMXファイルをアップロードして分析を開始してください。")

with st.expander("使い方"):
    st.markdown("""
    ### このアプリケーションの使い方
    
    1. 上部の「Browse files」ボタンをクリックしてTMXファイルをアップロードします。
    2. 必要に応じて「除外設定」で除外する原語・訳語ペアを設定します。
    3. アプリが自動的にファイルを分析し、結果を表示します。
    4. **分析結果の概要**: 各確認項目（大/小文字違い、大/小文字無視、単複の違い）について、要確認と判断されたセグメント数が表示されます。
    5. **分析結果テーブル**:
        - **ID**: 翻訳ユニットの通し番号。
        - **英語原文**: TMXファイル内の英語原文。
        - **日本語訳**: TMXファイル内の日本語訳。
        - **日本語訳に含まれる英単語**: 日本語訳から抽出された英単語のリスト。
        - **大/小文字無視**: 日本語訳中の英単語が、大文字・小文字を無視すると英語原文に存在しない場合に、その単語をリストアップします。
        - **大/小文字違い**: 日本語訳中の英単語が、大文字・小文字を区別すると英語原文に存在しないが、無視すると存在する場合に、原文の形と訳文の形を `原文/訳文` の形式でリストアップします (例: `Pod/pod`)。
        - **単複の違い**: 日本語訳中の英単語が、英語原文の単語と単数形・複数形のみ異なる場合（かつ完全一致ではない場合）に、そのペアを `原文の形/訳文の形` の形式でリストアップします (例: `book/books`)。
    6. **表示オプション**: テーブルに表示するセグメントをフィルタリングできます。
       - **すべて表示**: すべての翻訳セグメントと関連する分析結果列を表示します。
       - **要確認のみ(大/小文字違い)**: 「大/小文字違い」が検出されたセグメントのみを表示します。
       - **要確認のみ(大/小文字無視)**: 「大/小文字無視」で単語がリストアップされたセグメントのみを表示します。
       - **要確認のみ(単複の違い)**: 「単複の違い」が検出されたセグメントのみを表示します。
       - **いずれかの方法で要確認**: 上記のいずれかの「要確認」条件に合致するセグメントを表示します。
    7. 分析結果はCSV形式でダウンロードできます。
    
    ### 「要確認」の判断基準
    - **要確認(大/小文字無視)**: 「大/小文字無視」列に単語が1つ以上リストアップされた場合。
    - **要確認(大/小文字違い)**: 「大/小文字違い」列にペアが1つ以上リストアップされた場合。
    - **要確認(単複の違い)**: 「単複の違い」列にペアが1つ以上リストアップされた場合。

    ### 除外設定について
    
    「除外設定」では、特定の原語・訳語ペアを検出対象から除外できます。
    - 各行に「原語,訳語」の形式で入力します（例: `web,Web`）。
    - 正規表現を使用する場合は、パターンの前に `r:` を付けてください（例: `r:[A-Z][a-z]+,r:[A-Z][A-Z]+`）。
        - 正規表現では `\\` のように特殊文字をエスケープする必要があります。例えば、単語の境界を示す `\\b` や単語文字を示す `\\w` など。
    - 原語に指定した文字列（または正規表現パターン）が英語原文に含まれ、かつ訳語に指定した文字列（または正規表現パターン）が日本語訳に含まれる場合、そのセグメントは分析結果から除外されます。
    - **注意**: `CPUs/CPU` などのペアはデフォルトの正規表現 `r:\\b\\w+[^s]s\\b,r:\\b\\w+\\b` で除外されます。
    
    ### 英単語の抽出ルール
    - アルファベットが2文字以上連続するものを英単語として抽出します。
    - TMXファイルの構造が標準と異なる場合は、「TMXファイル構造（デバッグ）」を確認してください。
    """)
