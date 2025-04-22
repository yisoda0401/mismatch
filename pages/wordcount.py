import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io

# ページ設定（ワイドモード）
st.set_page_config(
    page_title="TMXファイル文字数カウントツール",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

def highlight_split_points(text):
    """
    文を分割できそうな箇所（「ため、」など）をハイライトするHTMLを生成する
    
    Parameters:
    -----------
    text : str
        ハイライト対象のテキスト
    
    Returns:
    --------
    str
        HTMLでハイライト処理されたテキスト
    """
    # 分割ポイントとなり得るフレーズのリスト
    split_phrases = [
        "ため、", "ので、", "から、", "ことから、", "ますが、", "ですが、", "あり、", "して、"
    ]
    
    # HTMLエスケープ
    import html
    escaped_text = html.escape(text)
    
    # フレーズの置換
    for phrase in split_phrases:
        escaped_phrase = html.escape(phrase)
        # 強調表示用のspanタグでラップ
        highlighted = f'<span style="background-color: #FFFF00; font-weight: bold;">{escaped_phrase}</span>'
        escaped_text = escaped_text.replace(escaped_phrase, highlighted)
    
    return escaped_text

def split_by_sentence(text):
    """
    テキストを句点「。」で分割して文ごとにリストを作成する
    
    Parameters:
    -----------
    text : str
        分割対象のテキスト
    
    Returns:
    --------
    list
        分割された文のリスト
    """
    # 句点「。」で文を分割する
    # 最後の句点の後に文字がない場合も考慮
    sentences = []
    parts = text.split('。')
    
    # 最後の空の部分を削除
    if parts and parts[-1] == '':
        parts = parts[:-1]
    
    # 句点を戻しつつリストに追加
    for part in parts:
        if part:  # 空でない部分のみ追加
            sentences.append(part + '。')
    
    # 文が一つも見つからない場合は元のテキストを返す
    if not sentences:
        return [text]
    
    return sentences

def count_characters_weighted(text):
    """
    文字数をカウントする際に、シングルバイト文字（英数字など）を0.5文字としてカウントする
    
    Parameters:
    -----------
    text : str
        カウント対象のテキスト
    
    Returns:
    --------
    float
        重み付けされた文字数
    """
    count = 0.0
    for char in text:
        # シングルバイト文字かどうかを判定
        if ord(char) < 256:  # ASCII文字とLatin-1補助文字はシングルバイト
            count += 0.5
        else:  # その他の文字（日本語など）は1文字としてカウント
            count += 1.0
    return count

def parse_tmx_file(uploaded_file):
    """
    TMXファイルを解析し、日本語訳文とその文字数を抽出する関数
    
    Parameters:
    -----------
    uploaded_file : UploadedFile
        Streamlitでアップロードされたファイルオブジェクト
    
    Returns:
    --------
    DataFrame
        セグメントID、日本語訳文、文字数を含むデータフレーム
    """
    content = uploaded_file.read()
    
    # XMLを解析
    root = ET.fromstring(content)
    
    # TMXのnamespaceがある場合に対応
    namespaces = {'': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}
    
    # 結果を格納するリスト
    results = []
    
    # TMXファイルの構造に応じて翻訳ユニットを抽出
    # 一般的なTMXファイルではbodyの中にtuがあり、tuの中にtuvがある
    body = root.find('.//body', namespaces)
    if body is None:
        return pd.DataFrame()
    
    # 各翻訳ユニット(tu)を処理
    for i, tu in enumerate(body.findall('./tu', namespaces)):
        # セグメントIDを取得（なければインデックスを使用）
        seg_id = tu.get('tuid') or f"segment_{i+1}"
        
        # 各言語バージョン(tuv)を処理
        for tuv in tu.findall('./tuv', namespaces):
            # 言語コードを確認
            lang = tuv.get('{http://www.w3.org/XML/1998/namespace}lang') or tuv.get('lang')
            
            # 日本語訳文を探す (ja, ja-JP, jpn などの可能性)
            if lang and ('ja' in lang.lower() or 'jpn' in lang.lower()):
                # segタグ内のテキストを取得
                seg = tuv.find('./seg', namespaces)
                if seg is not None:
                    # segタグの内容全体を取得（内部のタグも含めて）
                    if seg.text is None:
                        # segタグが空の場合
                        translation = ""
                    else:
                        # まずはテキスト部分を追加
                        translation = seg.text.strip()
                        
                        # 子要素があれば、その内容も全部追加
                        for child in seg.iter():
                            if child != seg:  # segタグ自体は除外
                                if child.text is not None:
                                    translation += child.text
                                if child.tail is not None:
                                    translation += child.tail
                    
                    # 空白文字の調整
                    translation = ' '.join(translation.split())
                    
                    # 文単位で分割
                    sentences = split_by_sentence(translation)
                    
                    # 各文のデータを記録
                    for i, sentence in enumerate(sentences):
                        # 文字数をカウント
                        char_count = count_characters_weighted(sentence)
                        
                        # 文IDを追加（複数文の場合は枝番をつける）
                        sentence_id = f"{seg_id}" if len(sentences) == 1 else f"{seg_id}_{i+1}"
                        
                        results.append({
                            'セグメントID': sentence_id,
                            '日本語訳文': sentence,
                            '文字数': char_count,
                            '原文分割': len(sentences) > 1  # 分割されたかどうかのフラグ
                        })
    
    # 結果をデータフレームに変換
    df = pd.DataFrame(results)
    return df

def main():
    st.title("TMXファイル解析アプリ")
    st.write("TMXファイルをアップロードして、指定文字数以上の日本語訳文を抽出します。")
    st.write("※ 英数字（シングルバイト文字）は0.5文字としてカウントされます。")
    st.write("※ 「ため、」などの文分割できそうな箇所は黄色でハイライト表示されます。")
    st.write("※ 句点「。」がある場合は文を自動的に分割し、個別にカウントします。")
    
    uploaded_file = st.file_uploader("TMXファイルをアップロード", type=["tmx"])
    
    min_chars = st.slider("最小文字数", min_value=10, max_value=500, value=100, step=10)
    
    if uploaded_file is not None:
        # ファイルを処理
        with st.spinner('TMXファイルを解析中...'):
            df = parse_tmx_file(uploaded_file)
        
        if df.empty:
            st.error("TMXファイルから日本語訳文を抽出できませんでした。ファイル形式を確認してください。")
        else:
            # 全体のセグメント数
            total_segments = len(df)
            
            # 文字数でフィルタリング
            filtered_df = df[df['文字数'] >= min_chars]
            
            # 結果を表示
            st.write(f"合計セグメント数: {total_segments}")
            st.write(f"{min_chars}文字以上のセグメント数: {len(filtered_df)}")
            
            if len(filtered_df) > 0:
                st.write("### 抽出された長い日本語訳文")
                st.write("注: 英数字（シングルバイト文字）は0.5文字としてカウントしています。")
                
                # セグメントID列を除外して表示用のデータフレームを作成
                display_df = filtered_df[['日本語訳文', '文字数', '原文分割']]
                
                    # カスタムHTMLとCSSを使用してテーブルを表示
                st.markdown("""
                <style>
                .custom-table {
                    width: 100%;
                    border-collapse: collapse;
                }
                .custom-table th, .custom-table td {
                    border: 1px solid #ddd;
                    padding: 8px;
                    text-align: left;
                }
                .custom-table th {
                    background-color: #f2f2f2;
                    font-weight: bold;
                }
                .custom-table tr:nth-child(even) {
                    background-color: #f9f9f9;
                }
                .custom-table tr:hover {
                    background-color: #f0f0f0;
                }
                .custom-table th:nth-child(1) {
                    width: 70%;
                }
                .custom-table th:nth-child(2) {
                    width: 15%;
                }
                .custom-table th:nth-child(3) {
                    width: 15%;
                }
                .split-row {
                    background-color: #ffecb3 !important;
                }
                </style>
                """, unsafe_allow_html=True)
                
                # HTMLテーブルを作成
                html_table = "<table class='custom-table'><thead><tr>"
                for col in display_df.columns:
                    html_table += f"<th>{col}</th>"
                html_table += "</tr></thead><tbody>"
                
                for _, row in display_df.iterrows():
                    # 分割された文かどうかに基づいてクラスを設定
                    row_class = " class='split-row'" if row.get('原文分割', False) else ""
                    html_table += f"<tr{row_class}>"
                    
                    # 訳文をハイライト処理して表示
                    highlighted_text = highlight_split_points(row['日本語訳文'])
                    html_table += f"<td>{highlighted_text}</td>"
                    html_table += f"<td>{row['文字数']}</td>"
                    
                    # 分割フラグがあれば表示
                    if '原文分割' in row:
                        split_text = "✅" if row['原文分割'] else ""
                        html_table += f"<td>{split_text}</td>"
                    
                    html_table += "</tr>"
                
                html_table += "</tbody></table>"
                
                html_table += "</tbody></table>"
                
                st.markdown(html_table, unsafe_allow_html=True)
                
                # CSVダウンロードボタン
                csv = filtered_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="CSVでダウンロード",
                    data=csv,
                    file_name='long_segments.csv',
                    mime='text/csv',
                )
            else:
                st.info(f"{min_chars}文字以上のセグメントが見つかりませんでした。")

if __name__ == "__main__":
    main()