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
    例: `web,Web` （原語に"web"が含まれ、訳語に"Web"が含まれる場合、このペアを検出対象から除外）
    """)
    exclusion_pairs_text = st.text_area(
        "除外ペア (各行に「原語,訳語」の形式で入力)",
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
        if source in en_text and target in ja_text:
            return True
    return False

def analyze_tmx(file_content, exclusion_pairs):
    try:
        # デバッグ情報を表示
        st.info("ファイルを解析中...")
        
        # XMLパーサーでファイルを解析
        tree = ET.parse(io.BytesIO(file_content))
        root = tree.getroot()
        
        # 名前空間を取得
        namespaces = dict([node for _, node in ET.iterparse(io.BytesIO(file_content), events=['start-ns'])])
        if not namespaces:
            # 名前空間がない場合はデフォルト設定
            namespaces['xml'] = 'http://www.w3.org/XML/1998/namespace'
        
        # デバッグ情報
        st.info(f"検出された名前空間: {namespaces}")
        st.info(f"ルート要素: {root.tag}")
        
        results = []
        excluded_count = 0
        
        # TMXファイルの構造に基づいて翻訳ユニットを探す
        tus = root.findall(".//tu") or root.findall(".//{*}tu")
        st.info(f"検出された翻訳ユニット数: {len(tus)}")
        
        for tu in tus:
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
                for word in ja_eng_words:
                    if word.lower() not in en_words_dict_case_insensitive:
                        missing_words_case_insensitive.append(word)
                
                results.append({
                    "英語原文": en_text,
                    "日本語訳": ja_text,
                    "日本語訳に含まれる英単語": ", ".join(ja_eng_words) if ja_eng_words else "なし",
                    "大/小文字区別: 原文に存在しない英単語": ", ".join(missing_words_case_sensitive) if missing_words_case_sensitive else "なし",
                    "大/小文字無視: 原文に存在しない英単語": ", ".join(missing_words_case_insensitive) if missing_words_case_insensitive else "なし",
                    "要確認(大/小文字区別)": len(missing_words_case_sensitive) > 0,
                    "要確認(大/小文字無視)": len(missing_words_case_insensitive) > 0
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

def display_with_details(df, index):
    """詳細表示用の関数: インデックスに対応する行の詳細を表示"""
    row = df.iloc[index]
    with st.expander(f"セグメント #{index+1} の詳細", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 英語原文")
            st.text_area("", value=row["英語原文"], height=68, key=f"en_text_{index}")
        with col2:
            st.markdown("### 日本語訳")
            st.text_area("", value=row["日本語訳"], height=68, key=f"ja_text_{index}")
        
        st.markdown("### 分析結果")
        col3, col4 = st.columns(2)
        with col3:
            st.markdown("**日本語訳に含まれる英単語:**")
            st.text(row["日本語訳に含まれる英単語"])
        
        with col4:
            st.markdown("**大/小文字区別: 原文に存在しない英単語:**")
            missing_words = row["大/小文字区別: 原文に存在しない英単語"]
            if row["要確認(大/小文字区別)"]:
                st.markdown(f"<span style='color:red'>{missing_words}</span>", unsafe_allow_html=True)
            else:
                st.text(missing_words)
            
            st.markdown("**大/小文字無視: 原文に存在しない英単語:**")
            missing_words = row["大/小文字無視: 原文に存在しない英単語"]
            if row["要確認(大/小文字無視)"]:
                st.markdown(f"<span style='color:red'>{missing_words}</span>", unsafe_allow_html=True)
            else:
                st.text(missing_words)

if uploaded_file is not None:
    file_content = uploaded_file.read()
    
    with st.spinner("TMXファイルを分析中..."):
        df = analyze_tmx(file_content, exclusion_pairs)
    
    if df is not None and not df.empty:
        # 分析結果の概要
        case_sensitive_count = df["要確認(大/小文字区別)"].sum()
        case_insensitive_count = df["要確認(大/小文字無視)"].sum()
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("要確認セグメント数 (大/小文字区別)", f"{case_sensitive_count} / {len(df)}")
        with col2:
            st.metric("要確認セグメント数 (大/小文字無視)", f"{case_insensitive_count} / {len(df)}")
        
        # データフレームを表示
        st.subheader("分析結果")
        
        # 「要確認」のフィルタリングオプション
        filter_option = st.radio(
            "表示オプション:",
            ["すべて表示", "要確認のみ(大/小文字区別)", "要確認のみ(大/小文字無視)", "いずれかの方法で要確認"],
            horizontal=True
        )
        
        # 表示モード選択
        display_mode = st.radio(
            "表示モード:",
            ["テーブル表示", "詳細表示"],
            horizontal=True
        )
        
        if filter_option == "要確認のみ(大/小文字区別)":
            filtered_df = df[df["要確認(大/小文字区別)"] == True]
        elif filter_option == "要確認のみ(大/小文字無視)":
            filtered_df = df[df["要確認(大/小文字無視)"] == True]
        elif filter_option == "いずれかの方法で要確認":
            filtered_df = df[(df["要確認(大/小文字区別)"] == True) | (df["要確認(大/小文字無視)"] == True)]
        else:
            filtered_df = df
        
        if display_mode == "テーブル表示":
            # テーブル表示モード
            # スタイル付きデータフレーム表示
            def highlight_missing(s):
                return ['background-color: #ffcccc' if v else '' for v in s]
            
            # 簡易表示用のデータフレームを作成（長いテキストは省略）
            display_df = filtered_df.copy()
            display_df["英語原文"] = display_df["英語原文"].apply(lambda x: (x[:100] + '...') if len(x) > 100 else x)
            display_df["日本語訳"] = display_df["日本語訳"].apply(lambda x: (x[:100] + '...') if len(x) > 100 else x)
            
            styled_df = display_df.style.apply(
                lambda x: highlight_missing(x == True), 
                subset=["要確認(大/小文字区別)", "要確認(大/小文字無視)"]
            )
            
            # データフレームを表示
            st.dataframe(styled_df, use_container_width=True)
            
        else:
            # 詳細表示モード
            st.write(f"全 {len(filtered_df)} 件のセグメントを表示")
            
            # 詳細表示用のページネーション
            items_per_page = 10
            page = st.number_input("ページ", min_value=1, max_value=max(1, (len(filtered_df) + items_per_page - 1) // items_per_page), value=1)
            start_idx = (page - 1) * items_per_page
            end_idx = min(start_idx + items_per_page, len(filtered_df))
            
            for i in range(start_idx, end_idx):
                display_with_details(filtered_df, i)
                st.divider()
        
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
    5. 表示モードを選択できます：
       - テーブル表示：一覧形式で確認（長いテキストは省略）
       - 詳細表示：折り返し可能なテキストエリアで原文と訳文を確認
    6. 「表示オプション」で結果を絞り込むことができます：
       - すべて表示：すべての翻訳セグメントを表示
       - 要確認のみ(大/小文字区別)：大文字小文字を区別して不一致がある行のみ表示
       - 要確認のみ(大/小文字無視)：大文字小文字を無視して不一致がある行のみ表示
       - いずれかの方法で要確認：いずれかの方法で不一致がある行を表示
    7. 分析結果はCSV形式でダウンロードできます
    
    ### 除外設定について
    
    「除外設定」では、特定の原語・訳語ペアを検出対象から除外できます。
    - 各行に「原語,訳語」の形式で入力します（例: `web,Web`）
    - 原語に指定した文字列が英語原文に含まれ、かつ訳語に指定した文字列が日本語訳に含まれる場合、そのセグメントは分析結果から除外されます
    - これにより、意図的に大文字小文字を変更している場合などを無視できます
    
    ### 分析について
    
    - **大/小文字区別**：「Example」と「example」を別の単語として扱います
    - **大/小文字無視**：「Example」と「example」を同じ単語として扱います
    - 英単語の抽出は2文字以上の連続したアルファベットを基準としています
    - TMXファイルの構造が標準と異なる場合は、「デバッグ情報」を確認してください
    """)