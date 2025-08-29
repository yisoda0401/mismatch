import streamlit as st
import pandas as pd
from translate.storage import tmx
import io
import re # ハイライト処理のために正規表現ライブラリをインポート

# --- デフォルト用語集 ---
# アプリケーションに内蔵されているサンプル用語集です。
# 形式: "Source,Target" のCSV形式文字列
DEFAULT_GLOSSARY_CSV = """Source,Target
deploy,展開
evict,削除
extract,デプロイメント
inject,挿入
metric,メトリック
overridden,上書き
override,上書き
overriding,上書き
secure,安全
unpack,デプロイメント
unzip,デプロイメント
configure,設定を設定
setting,設定を設定
"""

def highlight_text(text, term):
    """
    テキスト内の指定された用語（大文字・小文字を区別しない）をハイライトする関数。
    
    Args:
        text (str): 対象のテキスト。
        term (str): ハイライトする用語。
        
    Returns:
        str: 用語がHTMLの<mark>タグで囲まれたテキスト。
    """
    if not term or not text:
        return text
    
    # re.escapeで正規表現の特殊文字をエスケープし、安全に検索できるようにする
    # re.IGNORECASEで大文字・小文字を区別せずにマッチングする
    highlighted_text = re.sub(
        f'({re.escape(term)})', 
        r'<mark>\1</mark>', 
        text, 
        flags=re.IGNORECASE
    )
    return highlighted_text

def perform_check(tmx_file_content, glossary_df):
    """
    TMXファイルの内容をスキャンし、用語集の用語がソースとターゲットの両方に存在する場合を検出し、
    その用語をハイライトする関数。

    Args:
        tmx_file_content (bytes): アップロードされたTMXファイルのバイトデータ。
        glossary_df (pd.DataFrame): ソースとターゲットの用語を含むDataFrame。

    Returns:
        pd.DataFrame: 検出された用語使用箇所の情報を含むDataFrame。セグメントはハイライト済み。
    """
    found_segments = []
    
    try:
        tmx_file_obj = tmx.tmxfile(io.BytesIO(tmx_file_content))
    except Exception as e:
        st.error(f"TMXファイルの解析中にエラーが発生しました: {e}")
        return pd.DataFrame()

    for unit in tmx_file_obj.units:
        source_segment = unit.source
        target_segment = unit.target

        if not source_segment or not target_segment:
            continue
        
        for _, row in glossary_df.iterrows():
            source_term = str(row['Source']).strip()
            target_term = str(row['Target']).strip()

            if not source_term or not target_term:
                continue

            source_term_found = source_term.lower() in source_segment.lower()
            target_term_found = target_term.lower() in target_segment.lower()

            if source_term_found and target_term_found:
                # マッチした用語をハイライトする
                highlighted_source = highlight_text(source_segment, source_term)
                highlighted_target = highlight_text(target_segment, target_term)
                
                found_segments.append({
                    "原文用語": source_term,
                    "訳文用語": target_term,
                    "原文": highlighted_source,
                    "訳文": highlighted_target
                })

    return pd.DataFrame(found_segments)

def main():
    """
    StreamlitアプリケーションのメインUIとロジック。
    """
    st.set_page_config(layout="wide")
    st.title("TMX禁止用語チェッカー")
    st.markdown("TMXファイルをアップロードすると、自動的に用語集との照合が開始します。")

    # 結果表示テーブルの見た目を整えるためのCSS
    st.markdown("""
    <style>
    table {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed; /* テーブルのレイアウトを固定 */
    }
    th, td {
        border: 1px solid #e6e6e6;
        padding: 12px;
        text-align: left;
        vertical-align: top;
        word-wrap: break-word; /* 長い単語を折り返す */
    }
    th {
        background-color: #f2f2f2;
        text-align: left;
    }
    /* ★変更点: 1列目と2列目の幅を指定 */
    th:nth-child(1), td:nth-child(1) {
        width: 12%;
    }
    th:nth-child(2), td:nth-child(2) {
        width: 12%;
    }
    tr:nth-child(even) {
        background-color: #fafafa;
    }
    mark {
        background-color: #fff8ad; /* 黄色の背景色 */
        padding: 2px 4px;
        border-radius: 4px;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

    # --- サイドバー (用語集設定) ---
    st.sidebar.header("禁止用語の設定")
    glossary_option = st.sidebar.radio(
        "1. 使用する用語集を選択してください",
        ('デフォルトの用語集', 'CSVファイルをアップロード')
    )

    glossary_df = None
    if glossary_option == 'デフォルトの用語集':
        glossary_df = pd.read_csv(io.StringIO(DEFAULT_GLOSSARY_CSV))
        st.sidebar.write("使用中のデフォルト用語集:")
        st.sidebar.dataframe(glossary_df, hide_index=True, use_container_width=True)
        st.sidebar.write("追加する場合はこちら: https://docs.google.com/spreadsheets/d/1agQiUYggMyPxCyJlG7pCbBxCdYyhBUNTbPC-RSL4MuE/edit?gid=0#gid=0")
    else:
        glossary_file = st.sidebar.file_uploader(
            "用語集ファイル（CSV）をアップロード",
            type=['csv'],
            help="CSVファイルには 'Source' と 'Target' というヘッダーを持つ列が必要です。"
        )
        if glossary_file:
            try:
                glossary_df = pd.read_csv(glossary_file)
                if 'Source' not in glossary_df.columns or 'Target' not in glossary_df.columns:
                    st.sidebar.error("エラー: CSVファイルには 'Source' と 'Target' のカラムが必要です。")
                    glossary_df = None
                else:
                    st.sidebar.write("アップロードされた用語集:")
                    st.sidebar.dataframe(glossary_df, use_container_width=True)
            except Exception as e:
                st.sidebar.error(f"用語集ファイルの読み込みエラー: {e}")
                glossary_df = None

    # --- メイン画面 ---
    # st.markdown("---")
    # st.header("TMXファイルをアップロード")
    tmx_file = st.file_uploader("チェック対象のTMXファイルを選択してください", type=['tmx'], label_visibility="collapsed")
    
    if tmx_file is not None:
        if glossary_df is None or glossary_df.empty:
            st.warning("使用する用語集が読み込まれていません。サイドバーで用語集を選択してください。")
        else:
            with st.spinner("TMXファイルを処理中..."):
                tmx_file_content = tmx_file.getvalue()
                results_df = perform_check(tmx_file_content, glossary_df)

                st.subheader("チェック結果")
                if results_df.empty:
                    st.info("✅ 用語が使用されているセグメントは見つかりませんでした。")
                else:
                    st.success(f"✅ {len(results_df)}件の用語使用が確認されました。")
                    
                    # st.markdownでHTMLテーブルを表示
                    # これにより、<mark>タグがハイライトとして描画される
                    html_table = results_df.to_html(escape=False, index=False)
                    st.markdown(html_table, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
