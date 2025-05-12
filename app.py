import streamlit as st
import xml.etree.ElementTree as ET
import re
import pandas as pd
import io

# XML名前空間を登録
ET.register_namespace('xml', 'http://www.w3.org/XML/1998/namespace')

st.set_page_config(page_title="TMX分析ツール", layout="wide")
st.title("TMX分析ツール")
st.subheader("日本語訳に含まれる英単語が英語原文に存在するか確認")

uploaded_file = st.file_uploader("TMXファイルをアップロード", type=["tmx"])

# 除外ペアの入力エリア
with st.expander("除外設定", expanded=False):
    st.markdown("""
    ### 除外する原語・訳語ペアの設定

    以下の形式で除外したいペアを入力してください。各行に「原語,訳語」の形式で入力します。

    #### 基本的な使い方
    - 例: `web,Web` （原語に"web"が含まれ、訳語に"Web"が含まれる場合、このペアを検出対象から除外）

    #### 正規表現の使用方法
    正規表現を使用する場合は、パターンの前に `r:` を付けてください。
    - 例: `r:\\b\\w+[^s]s\\b,r:\\b\\w+\\b` （原語に複数形の単語があり、訳語が単数形の単語がある場合を除外）
    - 例: `r:[A-Z][a-z]+,r:[A-Z][A-Z]+` （原語に先頭大文字の単語があり、訳語に全て大文字の単語がある場合を除外）

    **注意**: 正規表現で `\\` のように特殊文字をエスケープする必要があります。例えば、単語の境界を示す `\\b` や単語文字を示す `\\w` など。

    正規表現と通常の文字列を組み合わせることも可能です。
    - 例: `Database,r:DB|データベース` （原語に"Database"が含まれ、訳語に"DB"または"データベース"が含まれる場合を除外）
    
    **注意**: maps/map、Insights/insight、CPUs/CPU などのペアはデフォルトで除外されます。除外しない場合は、下の正規表現 `r:\\b\\w+[^s]s\\b,r:\\b\\w+\\b` を削除してください。
    """)
    
    # デフォルトの除外ペア設定に正規表現の例を追加
    default_exclusion_pairs = """r:\\b\\w+[^s]s\\b,r:\\b\\w+\\b
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
        "除外ペア (各行に「原語,訳語」の形式で入力)",
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

def analyze_tmx(file_content, exclusion_pairs):
    try:
        # デバッグ情報を表示
        # st.info("ファイルを解析中...")
        
        # XMLパーサーでファイルを解析
        tree = ET.parse(io.BytesIO(file_content))
        root = tree.getroot()
        
        # 名前空間を取得
        namespaces = dict([node for _, node in ET.iterparse(io.BytesIO(file_content), events=['start-ns'])])
        if not namespaces:
            # 名前空間がない場合はデフォルト設定
            namespaces['xml'] = 'http://www.w3.org/XML/1998/namespace'
        
        # デバッグ情報
        # st.info(f"検出された名前空間: {namespaces}")
        # st.info(f"ルート要素: {root.tag}")
        
        results = []
        excluded_count = 0
        
        # TMXファイルの構造に基づいて翻訳ユニットを探す
        tus = root.findall(".//tu") or root.findall(".//{*}tu")
        # st.info(f"検出された翻訳ユニット数: {len(tus)}")
        
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
                
                # 大文字小文字を区別した分析
                # 英語セグメントから単語を抽出（大文字小文字を維持）
                en_words_case_sensitive = extract_english_words(en_text)
                
                # 大文字小文字を区別した辞書を作成（出現形を保持）
                en_words_dict_case_sensitive = {}
                for word in en_words_case_sensitive:
                    en_words_dict_case_sensitive[word] = word
                
                # 日本語セグメントから英単語を抽出
                ja_eng_words = extract_english_words(ja_text)
                
                missing_words_case_sensitive = []
                for word in ja_eng_words:
                    if word not in en_words_dict_case_sensitive:
                        missing_words_case_sensitive.append(word)
                
                # 大文字小文字を区別しない分析
                # 小文字変換した辞書を作成
                en_words_dict_case_insensitive = {}
                for word in en_words_case_sensitive:
                    en_words_dict_case_insensitive[word.lower()] = word
                
                missing_words_case_insensitive = []
                case_difference_words = []  # 大文字小文字だけが違う単語を格納
                
                for word in ja_eng_words:
                    word_lower = word.lower()
                    if word_lower not in en_words_dict_case_insensitive:
                        missing_words_case_insensitive.append(word)
                    # 大文字小文字を無視すれば存在するが、区別すると存在しない単語を検出
                    elif word not in en_words_dict_case_sensitive:
                        case_difference_words.append(f"{en_words_dict_case_insensitive[word_lower]}/{word}")
                
                results.append({
                    "ID": idx,  # 翻訳ユニットごとの一意のID
                    "英語原文": en_text,
                    "日本語訳": ja_text,
                    "日本語訳に含まれる英単語": ", ".join(ja_eng_words) if ja_eng_words else "なし",
                    "大/小文字区別": ", ".join(missing_words_case_sensitive) if missing_words_case_sensitive else "なし",
                    "大/小文字無視": ", ".join(missing_words_case_insensitive) if missing_words_case_insensitive else "なし",
                    "大/小文字違い": ", ".join(case_difference_words) if case_difference_words else "なし",
                    "要確認(大/小文字区別)": len(missing_words_case_sensitive) > 0,
                    "要確認(大/小文字無視)": len(missing_words_case_insensitive) > 0,
                    "要確認(大/小文字違い)": len(case_difference_words) > 0
                })
        
        if excluded_count > 0:
            st.info(f"除外条件に一致したセグメント数: {excluded_count}")
        
        if not results:
            st.warning("翻訳ペアが見つかりませんでした。TMXファイルの構造を確認してください。")
            # TMXファイルの構造を表示（デバッグ用）
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
        case_sensitive_count = df["要確認(大/小文字区別)"].sum()
        case_insensitive_count = df["要確認(大/小文字無視)"].sum()
        case_difference_count = df["要確認(大/小文字違い)"].sum()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("要確認セグメント数 (大/小文字区別)", f"{case_sensitive_count} / {len(df)}")
        with col2:
            st.metric("要確認セグメント数 (大/小文字無視)", f"{case_insensitive_count} / {len(df)}")
        with col3:
            st.metric("要確認セグメント数 (大/小文字違い)", f"{case_difference_count} / {len(df)}")
        
        # データフレームを表示
        st.subheader("分析結果")
        
        # 「要確認」のフィルタリングオプション
        filter_option = st.radio(
            "表示オプション:",
            ["すべて表示", 
             "要確認のみ(大/小文字区別)", 
             "要確認のみ(大/小文字無視)", 
             "要確認のみ(大/小文字違い)",
             "いずれかの方法で要確認"],
            index=4,  # 「いずれかの方法で要確認」がデフォルトで選択される
            horizontal=True
        )
        
        # フィルタリングを適用する部分
        if filter_option == "要確認のみ(大/小文字区別)":
            filtered_df = df[df["要確認(大/小文字区別)"] == True]
        elif filter_option == "要確認のみ(大/小文字無視)":
            filtered_df = df[df["要確認(大/小文字無視)"] == True]
        elif filter_option == "要確認のみ(大/小文字違い)":
            filtered_df = df[df["要確認(大/小文字違い)"] == True]
        elif filter_option == "いずれかの方法で要確認":
            filtered_df = df[(df["要確認(大/小文字区別)"] == True) | 
                             (df["要確認(大/小文字無視)"] == True) | 
                             (df["要確認(大/小文字違い)"] == True)]
        else:
            filtered_df = df
        
        # 表示する列を選択（IDは常に含める）
        base_columns = ["ID", "英語原文", "日本語訳"]
        
        # フィルタオプションに基づいて表示列を決定
        if filter_option == "要確認のみ(大/小文字区別)":
            columns_to_display = base_columns + ["大/小文字区別"]
        elif filter_option == "要確認のみ(大/小文字無視)":
            columns_to_display = base_columns + ["大/小文字無視"]
        elif filter_option == "要確認のみ(大/小文字違い)":
            columns_to_display = base_columns + ["大/小文字違い"]
        else:
            columns_to_display = base_columns + ["大/小文字区別", "大/小文字無視", "大/小文字違い"]
            
        # 表示用のデータフレームを作成（選択された列のみ）
        filtered_df = filtered_df[columns_to_display].copy()
        
        # st.tableを使用する代わりに、HTMLとCSSでスタイル付きのテーブルを作成
        html = """
        <style>
            .styled-table {
                border-collapse: collapse;
                width: 100%;
                font-size: 14px;
                text-align: left;
            }
            .styled-table th {
                background-color: #f2f2f2;
                color: #333;
                font-weight: bold;
                padding: 10px 8px;
                border: 1px solid #ddd;
            }
            .styled-table td {
                padding: 8px;
                border: 1px solid #ddd;
                word-wrap: break-word;
                max-width: 400px;
            }
            .styled-table tr:nth-child(even) {
                background-color: #f9f9f9;
            }
            .styled-table tr:nth-child(odd) {
                background-color: #ffffff;
            }
            .styled-table tr:hover {
                background-color: #e6f7ff;
            }
            .index-column {
                width: 50px;
                text-align: center;
                font-weight: bold;
            }
        </style>

        <table class="styled-table">
            <thead>
                <tr>
        """

        # テーブルヘッダーを作成
        for col in filtered_df.columns:
            # IDカラムには特別なクラスを適用
            if col == "ID":
                html += f"<th class=\"index-column\">{col}</th>"
            else:
                html += f"<th>{col}</th>"
        html += "</tr></thead><tbody>"

        # テーブルの行を作成
        for _, row in filtered_df.iterrows():
            html += "<tr>"
            for col in filtered_df.columns:
                cell_value = row[col]
                # IDカラムには特別なクラスを適用
                if col == "ID":
                    html += f"<td class=\"index-column\">{cell_value}</td>"
                # 「なし」という値は特別にスタイルを適用
                elif col in ["大/小文字区別", "大/小文字無視", "大/小文字違い"] and cell_value == "なし":
                    html += f"<td style='color: green;'>{cell_value}</td>"
                else:
                    html += f"<td>{cell_value}</td>"
            html += "</tr>"

        html += "</tbody></table>"

        # HTMLをレンダリング
        st.write(html, unsafe_allow_html=True)
        
        # ダウンロードボタン
        csv = filtered_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="CSV形式でダウンロード",
            data=csv,
            file_name="tmx_analysis_result.csv",
            mime="text/csv"
        )
    else:
        st.warning("分析可能なデータが見つかりませんでした。ファイル形式を確認してください。")
else:
    st.info("TMXファイルをアップロードして分析を開始してください。")

# 使い方の説明
with st.expander("使い方"):
    st.markdown("""
    ### このアプリケーションの使い方
    
    1. 上部の「Browse files」ボタンをクリックしてTMXファイルをアップロードします
    2. 必要に応じて「除外設定」で除外する原語・訳語ペアを設定します
    3. アプリが自動的にファイルを分析し、結果を表示します
    4. 「要確認」列が赤くハイライトされている行は、日本語訳に含まれる英単語が英語原文に存在しない可能性があります
       - すべて表示：すべての翻訳セグメントを表示
       - 要確認のみ(大/小文字区別)：大文字小文字を区別して不一致がある行のみ表示（「大/小文字区別」列のみ表示）
       - 要確認のみ(大/小文字無視)：大文字小文字を無視して不一致がある行のみ表示（「大/小文字無視」列のみ表示）
       - 要確認のみ(大/小文字違い)：大文字小文字のみが異なる単語がある行のみ表示（「大/小文字違い」列のみ表示）
       - いずれかの方法で要確認：いずれかの方法で不一致がある行を表示（すべての列を表示）
    5. 分析結果はCSV形式でダウンロードできます
    
    ### 除外設定について
    
    「除外設定」では、特定の原語・訳語ペアを検出対象から除外できます。
    - 各行に「原語,訳語」の形式で入力します（例: `web,Web`）
    - 正規表現を使用する場合は、パターンの前に `r:` を付けてください（例: `r:[A-Z][a-z]+,r:[A-Z][A-Z]+`）
    - 原語に指定した文字列（または正規表現パターン）が英語原文に含まれ、かつ訳語に指定した文字列（または正規表現パターン）が日本語訳に含まれる場合、そのセグメントは分析結果から除外されます
    - これにより、意図的に大文字小文字を変更している場合などを無視できます
    
    ### 分析について
    
    - **大/小文字区別**：「Example」と「example」を別の単語として扱います
    - **大/小文字無視**：「Example」と「example」を同じ単語として扱います
    - **大/小文字違い**：大文字小文字のみが異なる単語を検出します（例：原文に「example」があり訳文に「Example」がある場合）
    - 英単語の抽出は2文字以上の連続したアルファベットを基準としています
    - TMXファイルの構造が標準と異なる場合は、「デバッグ情報」を確認してください
    """)