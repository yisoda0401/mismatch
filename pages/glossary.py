import streamlit as st
import pandas as pd
from translate.storage import tmx
import io
import re # ハイライト処理のために正規表現ライブラリをインポート
import html # HTMLエスケープのためにインポート

def highlight_text(text, term, is_regex=False):
    """
    テキスト内の指定された用語または正規表現パターンをハイライトする関数。
    
    Args:
        text (str): 対象のテキスト。
        term (str): ハイライトする用語または正規表現パターン。
        is_regex (bool): termが正規表現かどうかを示すフラグ。
        
    Returns:
        str: マッチした箇所がHTMLの<mark>タグで囲まれたテキスト。
    """
    if not term or not text:
        return text
    
    # is_regexがFalseの場合（ペアチェック）、正規表現の特殊文字をエスケープする
    # is_regexがTrueの場合（訳文のみチェック）、入力をそのままパターンとして使用する
    pattern = term if is_regex else re.escape(term)
    
    try:
        # re.IGNORECASEで大文字・小文字を区別せずにマッチングする
        highlighted_text = re.sub(
            f'({pattern})', 
            r'<mark>\1</mark>', 
            text, 
            flags=re.IGNORECASE
        )
        return highlighted_text
    except re.error:
        # 無効な正規表現パターンが指定された場合は、ハイライトせず元のテキストを返す
        # エラーメッセージは呼び出し元の`perform_check`で表示する
        return text

def perform_check(tmx_file_content, glossary_data, check_mode):
    """
    TMXファイルの内容をスキャンし、指定されたモードに応じて用語を検出・ハイライトする関数。

    Args:
        tmx_file_content (bytes): アップロードされたTMXファイルのバイトデータ。
        glossary_data (pd.DataFrame or list): 用語集データ（DataFrameまたはリスト）。
        check_mode (str): 'ペアチェック（原文と訳文）' または '訳文のみチェック'。

    Returns:
        pd.DataFrame: 検出された用語使用箇所の情報を含むDataFrame。セグメントはハイライト済み。
    """
    found_segments = []
    invalid_patterns = set() # 無効な正規表現を一度だけ警告するためのセット
    
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
        
        # チェックモードに応じて処理を分岐
        if check_mode == 'ペアチェック（原文と訳文）':
            for _, row in glossary_data.iterrows():
                source_term = str(row['Source']).strip()
                target_term = str(row['Target']).strip()

                if not source_term or not target_term:
                    continue

                source_term_found = source_term.lower() in source_segment.lower()
                target_term_found = target_term.lower() in target_segment.lower()

                if source_term_found and target_term_found:
                    # is_regexはデフォルトでFalseなので、従来通り動作する
                    highlighted_source = highlight_text(source_segment, source_term)
                    highlighted_target = highlight_text(target_segment, target_term)
                    
                    found_segments.append({
                        "原文用語": html.escape(source_term),
                        "訳文用語": html.escape(target_term),
                        "原文": highlighted_source,
                        "訳文": highlighted_target
                    })
        
        elif check_mode == '訳文のみチェック':
            for term in glossary_data:
                target_term_pattern = term.strip()
                if not target_term_pattern:
                    continue

                try:
                    # 正規表現で検索
                    if re.search(target_term_pattern, target_segment, flags=re.IGNORECASE):
                        # ハイライト処理（正規表現モードを有効にする）
                        highlighted_target = highlight_text(target_segment, target_term_pattern, is_regex=True)
                        
                        found_segments.append({
                            "原文用語": "ー", # 訳文のみチェックのため該当なし
                            "訳文用語": html.escape(target_term_pattern), # パターンそのものを表示
                            "原文": html.escape(source_segment), # ハイライトなし
                            "訳文": highlighted_target
                        })
                except re.error:
                    # 無効な正規表現パターンを一度だけ警告する
                    if target_term_pattern not in invalid_patterns:
                        st.sidebar.error(f"無効な正規表現: '{target_term_pattern}'")
                        invalid_patterns.add(target_term_pattern)


    return pd.DataFrame(found_segments)

def main():
    """
    StreamlitアプリケーションのメインUIとロジック。
    """
    st.set_page_config(layout="wide")
    st.title("TMX用語チェッカー")
    st.markdown("サイドバーでチェックモードと用語集を設定し、TMXファイルをアップロードしてください。")

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
    st.sidebar.header("設定")
    check_mode = st.sidebar.radio(
        "チェックモードを選択",
        ('ペアチェック（原文と訳文）', '訳文のみチェック'),
        key="check_mode"
    )

    glossary_data = None
    is_glossary_ready = False

    if check_mode == 'ペアチェック（原文と訳文）':
        st.sidebar.markdown("---")
        st.sidebar.subheader("用語ペアを入力")
        
        # デフォルトで表示するテキストエリアのテキスト
        default_pair_text = """deploy,展開
evict,削除
evict,エビクト
eviction,エビクション
extract,デプロイメント
inject,挿入
metric,メトリック
overridden,上書き
override,上書き
overriding,上書き
secure,安全
unpack,デプロイメント
unzip,デプロイメント
update,更新プログラム
deprecate,廃止
toleration,容認
drain,ドレイン
anti-affinity,非アフィニティー
graceful,正常
channel,チャンネル
"""

        pair_terms_input = st.sidebar.text_area(
            "1行に1ペアを「原文,訳文」の形式で入力してください",
            default_pair_text,
            height=250,
            help="カンマ区切りで原文と訳文を入力します。"
        )
        if pair_terms_input:
            pairs = []
            lines = pair_terms_input.strip().split('\n')
            is_valid_format = True
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                parts = [p.strip() for p in line.split(',')]
                if len(parts) == 2 and parts[0] and parts[1]:
                    pairs.append({'Source': parts[0], 'Target': parts[1]})
                else:
                    st.sidebar.error(f"エラー: {i+1}行目の形式が正しくありません。「原文,訳文」の形式で入力してください。")
                    is_valid_format = False
                    break # エラーが見つかったら処理を停止
            
            if is_valid_format and pairs:
                glossary_data = pd.DataFrame(pairs)
                st.sidebar.write("チェック中の用語集:")
                st.sidebar.dataframe(glossary_data, use_container_width=True, hide_index=True)
                st.sidebar.write("用語の追加はこちら: https://docs.google.com/spreadsheets/d/1agQiUYggMyPxCyJlG7pCbBxCdYyhBUNTbPC-RSL4MuE/edit?gid=0#gid=0")
                is_glossary_ready = True
            elif not is_valid_format:
                is_glossary_ready = False


    else: # 訳文のみチェック
        st.sidebar.markdown("---")
        st.sidebar.subheader("訳文内をチェックする用語/正規表現")
        
        # デフォルトのテキストに正規表現の例を追加
        default_regex_text = """設定の設定
設定を設定
クエリーし
クエリーす
クエリーせ
クエリーでき
(?<!:|-)\\s参照し
(?<!:|-)\\s選択し
(?<!:|-)\\sクリックし
\\s~\\s"""
        
        target_terms_input = st.sidebar.text_area(
            "1行に1つずつ用語または正規表現を入力",
            default_regex_text,
            height=200,
            help="正規表現を使用して、より複雑なパターン（例: `(設定)\\s*\\1+` で「設定設定」のような重複を検索）を検出できます。"
        )
        if target_terms_input:
            glossary_data = [term.strip() for term in target_terms_input.split('\n') if term.strip()]
            if glossary_data:
                st.sidebar.write("チェック中の用語/パターン:")
                st.sidebar.dataframe(glossary_data, column_config={"value": "用語/パターン"}, use_container_width=True)
                is_glossary_ready = True

    # --- メイン画面 ---
    tmx_file = st.file_uploader("チェック対象のTMXファイルを選択してください", type=['tmx'], label_visibility="collapsed")
    
    if tmx_file is not None:
        if not is_glossary_ready:
            st.warning("使用する用語集が読み込まれていません。サイドバーで用語集を設定してください。")
        else:
            with st.spinner("TMXファイルを処理中..."):
                tmx_file_content = tmx_file.getvalue()
                results_df = perform_check(tmx_file_content, glossary_data, check_mode)

                st.subheader("チェック結果")
                if results_df.empty:
                    st.info("✅ 条件に一致するセグメントは見つかりませんでした。")
                else:
                    # 結果が見つかった場合のメッセージをモードによって変更
                    if check_mode == '訳文のみチェック':
                        st.success(f"✅ 訳文内に {len(results_df)}件のパターン一致が確認されました。")
                    else:
                        st.success(f"✅ {len(results_df)}件の用語ペア使用が確認されました。")

                    # to_htmlでHTMLテーブルに変換し、st.markdownで表示
                    # これにより、<mark>タグがハイライトとして描画される
                    html_table = results_df.to_html(escape=False, index=False)
                    st.markdown(html_table, unsafe_allow_html=True)

if __name__ == "__main__":
    main()

