import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
import difflib # 差分比較のためにdifflibをインポート

def get_full_text(element):
    """
    指定されたXML要素内のすべてのテキスト（子要素を含む）を連結して返す。
    """
    if element is None:
        return ""
    # itertext() は要素内のすべてのテキストノードを再帰的に取得します
    return "".join(element.itertext()).strip().replace('\n', ' ').replace('\r', '')

def extract_segments(xml_content):
    """
    XMLコンテンツから<literal>タグを含むセグメントを抽出する。
    セグメントは、<literal>タグの親要素によって定義される。
    """
    segments = []
    # XMLパース時のエラーをハンドル
    try:
        # 文字列の先頭にある可能性のあるBOM（バイトオーダーマーク）を削除
        if xml_content.startswith('\ufeff'):
            xml_content = xml_content[1:]
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        st.error(f"XMLの解析に失敗しました: {e}")
        return None

    # DocBookのデフォルトネームスペースを定義
    # findallなどでタグを検索する際に必要
    namespace = {'db': 'http://docbook.org/ns/docbook'}
    
    # --- 親要素を取得するためのマップを作成 ---
    # XPathの'..'が古いバージョンのPythonでサポートされていない問題への対策
    parent_map = {c: p for p in root.iter() for c in p}
    
    # すべての<literal>タグの親要素を重複なく、ドキュメント順に取得
    parent_elements = []
    seen_parents = set()
    # .// を使うことで、ルート要素から見て任意の子孫要素を検索
    for literal_element in root.findall('.//db:literal', namespace):
        # --- マップから親要素を取得 ---
        parent = parent_map.get(literal_element)
        if parent is not None and parent not in seen_parents:
            parent_elements.append(parent)
            seen_parents.add(parent)

    # 抽出した親要素ごとにセグメント情報を作成
    for parent in parent_elements:
        parent_text = get_full_text(parent)
        
        # 親要素に直接含まれる<literal>タグの内容を取得
        literal_tags = parent.findall('db:literal', namespace)
        
        # <literal>タグ内のテキストをsetとして保存（順不同の比較のため）
        # <literal>タグ内にさらに子要素がある場合も考慮してget_full_textを使用
        literals_text_set = {get_full_text(lit) for lit in literal_tags}
        
        segments.append({
            'parent_text': parent_text,
            'literals': literals_text_set
        })
        
    return segments

def generate_diff_html(source_text, target_text):
    """
    2つのテキストを比較し、差分をハイライトしたHTMLを生成する。
    """
    sm = difflib.SequenceMatcher(None, source_text, target_text)
    source_html = []
    target_html = []
    
    # ===== 修正箇所 START =====
    # スタイル定義から取り消し線を削除
    style_delete = 'style="background-color: #ffdddd;"'
    # ===== 修正箇所 END =====
    style_insert = 'style="background-color: #ddffdd;"'

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            source_html.append(source_text[i1:i2])
            target_html.append(target_text[j1:j2])
        elif tag == 'delete':
            source_html.append(f'<span {style_delete}>{source_text[i1:i2]}</span>')
        elif tag == 'insert':
            target_html.append(f'<span {style_insert}>{target_text[j1:j2]}</span>')
        elif tag == 'replace':
            source_html.append(f'<span {style_delete}>{source_text[i1:i2]}</span>')
            target_html.append(f'<span {style_insert}>{target_text[j1:j2]}</span>')
            
    return f'<div>{"".join(source_html)}</div>', f'<div>{"".join(target_html)}</div>'

# --- Streamlit UI部分 ---
st.set_page_config(layout="wide")

st.title('XML `<literal>` タグ比較ツール')
st.write("""
翻訳前（ソース）と翻訳後（ターゲット）のXMLファイルをアップロードしてください。
このアプリは、対応する各セグメント内の`<literal>`タグの内容を比較し、
翻訳によって変更されてはいけない文字列（例: `kinit`）が変更されていないかを確認します。
""")

# session_stateを初期化して、比較結果を保持できるようにする
if 'comparison_run' not in st.session_state:
    st.session_state.comparison_run = False
    st.session_state.results_df = pd.DataFrame()
    st.session_state.mismatch_count = 0
    st.session_state.total_segments = 0
    st.session_state.results_found = False

col1, col2 = st.columns(2)

with col1:
    source_file = st.file_uploader("1. ソースXMLファイルをアップロード", type="xml")

with col2:
    target_file = st.file_uploader("2. ターゲットXMLファイルをアップロード", type="xml")

if st.button("比較を実行する", use_container_width=True):
    # ボタンが押されたら、まず以前の結果をリセットする
    st.session_state.comparison_run = False
    if source_file is not None and target_file is not None:
        with st.spinner("ファイルを処理・比較しています..."):
            # アップロードされたファイルを読み込む
            source_content = source_file.getvalue().decode("utf-8")
            target_content = target_file.getvalue().decode("utf-8")

            # 各ファイルからセグメントを抽出
            source_segments = extract_segments(source_content)
            target_segments = extract_segments(target_content)

            # 抽出が成功した場合のみ処理を続行
            if source_segments is not None and target_segments is not None:
                # セグメント数が異なる場合はエラーを表示
                if len(source_segments) != len(target_segments):
                    st.error(
                        f"エラー: 抽出されたセグメントの数が異なります。"
                        f"ソース: {len(source_segments)}セグメント, "
                        f"ターゲット: {len(target_segments)}セグメント。"
                        "ファイルの構造が同一であることを確認してください。"
                    )
                else:
                    results_data = []
                    mismatch_count = 0
                    # すべてのセグメントをループして結果リストを作成
                    for i, source_seg in enumerate(source_segments):
                        target_seg = target_segments[i]
                        
                        is_match = source_seg['literals'] == target_seg['literals']
                        if not is_match:
                            mismatch_count += 1
                        
                        source_literals_str = ", ".join(sorted(list(source_seg['literals'])))
                        target_literals_str = ", ".join(sorted(list(target_seg['literals'])))
                        
                        source_display = source_literals_str
                        target_display = target_literals_str

                        if not is_match:
                            # 不一致の場合、HTML差分を生成する
                            source_display, target_display = generate_diff_html(source_literals_str, target_literals_str)

                        results_data.append({
                            "状態": "✅ 一致" if is_match else "❌ 不一致",
                            "ソースセグメント": source_seg['parent_text'],
                            "ターゲットセグメント": target_seg['parent_text'],
                            "ソースのliteral": source_display, # 差分表示を格納
                            "ターゲットのliteral": target_display, # 差分表示を格納
                        })
                    
                    # 結果をsession_stateに保存する
                    st.session_state.comparison_run = True
                    if results_data:
                        df = pd.DataFrame(results_data)
                        df = df[["状態", "ソースセグメント", "ターゲットセグメント", "ソースのliteral", "ターゲットのliteral"]]
                        st.session_state.results_df = df
                        st.session_state.mismatch_count = mismatch_count
                        st.session_state.total_segments = len(results_data)
                        st.session_state.results_found = True
                    else:
                        st.session_state.results_found = False

    else:
        st.warning("ソースとターゲット、両方のXMLファイルをアップロードしてください。")
        st.session_state.comparison_run = False


# 比較が実行された後、常にこのブロックで結果を表示する
if st.session_state.comparison_run:
    if st.session_state.results_found:
        mismatch_count = st.session_state.mismatch_count
        df = st.session_state.results_df
        total_segments = st.session_state.total_segments
        
        if mismatch_count > 0:
            st.warning(f"{mismatch_count}件の不一致が見つかりました。")
        else:
            st.success("素晴らしい！`<literal>`タグの内容に不一致は見つかりませんでした。")
        
        if mismatch_count > 0:
            show_only_mismatches = st.checkbox("不一致のみ表示する", value=True)
        else:
            show_only_mismatches = False

        if show_only_mismatches:
            df_to_display = df[df['状態'] == '❌ 不一致']
            st.info(f"{len(df_to_display)}件の不一致項目をフィルタリングして表示します。")
        else:
            df_to_display = df
            st.info(f"全 {total_segments} セグメントの比較結果を表示します。")

        # 不一致行の背景色ハイライトを削除し、インデックスを非表示にする
        st.markdown(
            df_to_display.style.hide(axis="index").to_html(escape=False),
            unsafe_allow_html=True
        )
    else:
        st.info("比較対象となる`<literal>`タグを含むセグメントが見つかりませんでした。")

