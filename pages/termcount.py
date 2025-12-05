import streamlit as st
import pandas as pd
import io

# ページ設定
st.set_page_config(
    page_title="用語カウントツール",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

def count_term_occurrences(terms_df, tm_df, source_col_idx, target_col_idx, case_sensitive):
    """
    用語集の用語が翻訳メモリ(TM)に出現する回数をカウントする関数。
    
    Args:
        terms_df (DataFrame): 用語集データフレーム
        tm_df (DataFrame): 翻訳メモリデータフレーム
        source_col_idx (int): 用語集の検索対象列インデックス
        target_col_idx (int): TMの検索対象列インデックス
        case_sensitive (bool): 大文字小文字を区別するか
    
    Returns:
        DataFrame: 用語とカウント結果を含むデータフレーム
    """
    results = []
    
    # 用語集から用語を取得
    terms = terms_df.iloc[:, source_col_idx].dropna().astype(str).tolist()
    
    # TMのターゲット列を取得
    tm_contents = tm_df.iloc[:, target_col_idx].dropna().astype(str).tolist()
    
    # 大文字小文字を区別しない場合は前処理
    if not case_sensitive:
        tm_contents = [content.lower() for content in tm_contents]
    
    # プログレスバーの設定
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    total_terms = len(terms)
    
    for i, term in enumerate(terms):
        if not case_sensitive:
            term_search = term.lower()
        else:
            term_search = term
        
        count = 0
        for segment in tm_contents:
            count += segment.count(term_search)
        
        results.append({
            '用語': term,
            '出現回数': count
        })
        
        # プログレスバーの更新
        progress = (i + 1) / total_terms
        progress_bar.progress(progress)
        status_text.text(f"処理中... {i + 1}/{total_terms} 用語")
    
    # プログレスバーをクリア
    progress_bar.empty()
    status_text.empty()
    
    return pd.DataFrame(results)


def main():
    st.title("📊 用語カウントツール")
    st.markdown("""
    用語集の用語が翻訳メモリ（TM）に何回出現するかをカウントします。
    """)
    
    # サイドバーに設定オプション
    with st.sidebar:
        st.header("⚙️ 設定")
        
        case_sensitive = st.checkbox(
            "大文字小文字を区別する",
            value=False,
            help="チェックを外すと、大文字小文字を区別せずにカウントします"
        )
        
        st.divider()
        
        st.markdown("""
        ### 📖 使い方
        1. **用語集CSV**をアップロード
        2. **翻訳メモリCSV**をアップロード
        3. 各ファイルの検索対象列を選択
        4. **カウント実行**ボタンをクリック
        5. 結果を確認してダウンロード
        """)
    
    # ファイルアップロードセクション
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📝 用語集CSVファイル")
        glossary_file = st.file_uploader(
            "用語集をアップロード",
            type=["csv"],
            key="glossary",
            help="用語が含まれるCSVファイルをアップロードしてください"
        )
        
        if glossary_file is not None:
            try:
                glossary_df = pd.read_csv(glossary_file, encoding='utf-8-sig')
                st.success(f"✅ {len(glossary_df)} 行のデータを読み込みました")
                
                # 列選択
                glossary_columns = glossary_df.columns.tolist()
                glossary_col = st.selectbox(
                    "検索する用語が含まれる列を選択",
                    options=range(len(glossary_columns)),
                    format_func=lambda x: f"{x+1}列目: {glossary_columns[x]}",
                    key="glossary_col"
                )
                
                # プレビュー表示
                with st.expander("データプレビュー", expanded=False):
                    st.dataframe(glossary_df.head(10), width='stretch')
            except Exception as e:
                st.error(f"ファイルの読み込みに失敗しました: {e}")
                glossary_df = None
        else:
            glossary_df = None
    
    with col2:
        st.subheader("📚 翻訳メモリCSVファイル")
        tm_file = st.file_uploader(
            "翻訳メモリをアップロード",
            type=["csv"],
            key="tm",
            help="翻訳メモリ（TM）のCSVファイルをアップロードしてください"
        )
        
        if tm_file is not None:
            try:
                tm_df = pd.read_csv(tm_file, encoding='utf-8-sig')
                st.success(f"✅ {len(tm_df)} 行のセグメントを読み込みました")
                
                # 列選択
                tm_columns = tm_df.columns.tolist()
                tm_col = st.selectbox(
                    "検索対象の列を選択",
                    options=range(len(tm_columns)),
                    format_func=lambda x: f"{x+1}列目: {tm_columns[x]}",
                    index=min(1, len(tm_columns)-1),  # デフォルトで2列目を選択
                    key="tm_col"
                )
                
                # プレビュー表示
                with st.expander("データプレビュー", expanded=False):
                    st.dataframe(tm_df.head(10), width='stretch')
            except Exception as e:
                st.error(f"ファイルの読み込みに失敗しました: {e}")
                tm_df = None
        else:
            tm_df = None
    
    st.divider()
    
    # カウント実行ボタン
    if glossary_file is not None and tm_file is not None:
        if st.button("🔍 カウント実行", type="primary", width='stretch'):
            with st.spinner("カウント処理を実行中..."):
                try:
                    result_df = count_term_occurrences(
                        glossary_df, 
                        tm_df, 
                        glossary_col, 
                        tm_col,
                        case_sensitive
                    )
                    
                    # セッションステートに結果を保存
                    st.session_state.result_df = result_df
                    st.success("✅ カウントが完了しました！")
                    
                except Exception as e:
                    st.error(f"処理中にエラーが発生しました: {e}")
    else:
        st.info("👆 両方のCSVファイルをアップロードしてください")
    
    # 結果の表示
    if 'result_df' in st.session_state and st.session_state.result_df is not None:
        st.subheader("📊 カウント結果")
        
        result_df = st.session_state.result_df
        
        # 統計情報の表示
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("総用語数", len(result_df))
        with col2:
            st.metric("出現あり", len(result_df[result_df['出現回数'] > 0]))
        with col3:
            st.metric("出現なし", len(result_df[result_df['出現回数'] == 0]))
        with col4:
            st.metric("合計出現回数", result_df['出現回数'].sum())
        
        # フィルタリングオプション
        filter_option = st.radio(
            "表示フィルター:",
            ["すべて表示", "出現あり（1回以上）のみ", "出現なし（0回）のみ"],
            horizontal=True
        )
        
        if filter_option == "出現あり（1回以上）のみ":
            display_df = result_df[result_df['出現回数'] > 0]
        elif filter_option == "出現なし（0回）のみ":
            display_df = result_df[result_df['出現回数'] == 0]
        else:
            display_df = result_df
        
        # ソートオプション
        sort_option = st.selectbox(
            "並び替え:",
            ["元の順序", "出現回数（多い順）", "出現回数（少ない順）", "用語名（昇順）", "用語名（降順）"]
        )
        
        if sort_option == "出現回数（多い順）":
            display_df = display_df.sort_values('出現回数', ascending=False)
        elif sort_option == "出現回数（少ない順）":
            display_df = display_df.sort_values('出現回数', ascending=True)
        elif sort_option == "用語名（昇順）":
            display_df = display_df.sort_values('用語', ascending=True)
        elif sort_option == "用語名（降順）":
            display_df = display_df.sort_values('用語', ascending=False)
        
        # データフレームの表示
        st.dataframe(
            display_df,
            width='stretch',
            hide_index=True,
            column_config={
                "用語": st.column_config.TextColumn("用語", width="large"),
                "出現回数": st.column_config.NumberColumn(
                    "出現回数",
                    width="small",
                    format="%d"
                )
            }
        )
        
        st.caption(f"表示中: {len(display_df)} 件 / 全 {len(result_df)} 件")
        
        # ダウンロードボタン
        csv = result_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 結果をCSVでダウンロード",
            data=csv,
            file_name="term_counts_result.csv",
            mime="text/csv",
            width='stretch'
        )


if __name__ == "__main__":
    main()

