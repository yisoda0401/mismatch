import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET

# ページ設定（ワイドモード）
st.set_page_config(
    page_title="TMX英語低単語数セグメント検出ツール (改)",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

def count_words(text):
    """
    テキスト内の単語数をカウントする（スペースで分割）
    """
    if not text or text.isspace():
        return 0
    return len(text.split())

def get_segment_text(seg_element):
    """
    seg要素から内部のテキストを連結して取得する
    """
    text_parts = []
    if seg_element.text:
        text_parts.append(seg_element.text.strip())
    for child in seg_element:
        if child.text:
            text_parts.append(child.text.strip())
        if child.tail:
            text_parts.append(child.tail.strip())
    return ' '.join(filter(None, text_parts))


def parse_tmx_file_for_english_source_with_translation(uploaded_file):
    """
    TMXファイルを解析し、セグメントID（簡素化）、英語原文の単語数、
    英語原文、および対応する日本語訳文を抽出する関数
    """
    content = uploaded_file.read()

    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        st.error(f"XML解析エラー: {e}")
        return pd.DataFrame()

    namespaces = {'': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}
    namespaces['xml'] = 'http://www.w3.org/XML/1998/namespace'

    results = []

    body = root.find('.//body', namespaces)
    if body is None:
        st.warning("TMXファイル内に <body> タグが見つかりませんでした。")
        return pd.DataFrame()

    for i, tu in enumerate(body.findall('./tu', namespaces)):
        raw_tuid = tu.get('tuid')
        seg_id = ""
        if raw_tuid:
            if raw_tuid.startswith("segment_"):
                seg_id = raw_tuid[len("segment_"):]
            elif raw_tuid.startswith("Segment_"): # 大文字の "Segment_" も考慮
                seg_id = raw_tuid[len("Segment_"):]
            else:
                seg_id = raw_tuid
        else:
            seg_id = str(i + 1) # tuidがない場合は連番のみ

        english_source_text = None
        japanese_translation_text = ""

        for tuv in tu.findall('./tuv', namespaces):
            lang_attr = f"{{{namespaces['xml']}}}lang"
            lang = tuv.get(lang_attr)

            seg = tuv.find('./seg', namespaces)
            if seg is not None:
                current_seg_text = get_segment_text(seg)

                if lang and lang.lower().startswith('en'):
                    english_source_text = current_seg_text
                elif lang and ('ja' in lang.lower() or 'jpn' in lang.lower()):
                    japanese_translation_text = current_seg_text

        if english_source_text is not None:
            word_count = count_words(english_source_text)
            results.append({
                'セグメントID': seg_id,
                '単語数': word_count, # DataFrame内では数値として保持
                '英語原文': english_source_text,
                '日本語訳文': japanese_translation_text,
            })

    if not results:
        st.info("解析可能な英語の翻訳単位 (tu) が見つかりませんでした。")

    df_columns = ['セグメントID', '単語数', '英語原文', '日本語訳文']
    df = pd.DataFrame(results, columns=df_columns)
    return df

def main():
    st.title("TMXファイル 英語低単語数セグメント検出")
    st.write("TMXファイルをアップロードして、指定単語数以下の英語原文セグメントを抽出します。表のヘッダーをクリックしてソートできます。")
    st.write("※ 単語数はスペース区切りでカウントされます。")

    uploaded_file = st.file_uploader("TMXファイルをアップロード", type=["tmx"])

    max_words_slider = st.slider("英語原文の最大単語数", min_value=1, max_value=100, value=2, step=1)

    if uploaded_file is not None:
        with st.spinner('TMXファイルを解析中...'):
            df = parse_tmx_file_for_english_source_with_translation(uploaded_file)

        if df.empty:
            st.warning("データフレームが空です。ファイル内容を確認するか、別のファイルでお試しください。")
        else:
            total_segments = len(df)
            
            # フィルタリング前に単語数列を文字列に変換する場合（ソート挙動に注意）
            # df_display = df.copy()
            # df_display['単語数'] = df_display['単語数'].astype(str)
            # filtered_df = df_display[df_display['単語数'].astype(int) <= max_words_slider].copy()
            
            # DataFrame内の単語数は数値のままフィルタリング
            filtered_df = df[df['単語数'] <= max_words_slider].copy()


            st.write(f"検出された英語セグメント総数（対応訳文含む）: {total_segments}")
            st.write(f"最大 {max_words_slider}単語の英語セグメント数: {len(filtered_df)}")

            if len(filtered_df) > 0:
                st.write("### 抽出結果（ヘッダーをクリックしてソート）")
                
                # 表示用に単語数列を文字列型に変換して左寄せにする
                # ただし、ソートは文字列として行われる点に注意が必要
                # filtered_df_display = filtered_df.copy()
                # filtered_df_display['単語数'] = filtered_df_display['単語数'].astype(str)

                st.dataframe(
                    filtered_df, # 元のfiltered_df (単語数は数値型) を渡す
                    column_config={
                        "セグメントID": st.column_config.TextColumn(
                            "ID",
                            help="翻訳単位ID（TMX内のtuidまたは連番）",
                            width="small"
                        ),
                        "単語数": st.column_config.TextColumn( # NumberColumnからTextColumnに変更
                            "単語数 (英)",
                            help="英語原文の単語数。この列でフィルタリングされています。",
                            # format パラメータは TextColumn にはないため削除
                            width="small"
                        ),
                        "英語原文": st.column_config.TextColumn(
                            "英語原文 (Source)",
                            help="原文の英語テキスト",
                            width="large"
                        ),
                        "日本語訳文": st.column_config.TextColumn(
                            "日本語訳文 (Target)",
                            help="対応する日本語訳文テキスト",
                            width="large"
                        ),
                    },
                    use_container_width=True,
                    hide_index=True
                )

                csv = filtered_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="CSVでダウンロード (表示結果)",
                    data=csv,
                    file_name=f'short_english_segments_max_{max_words_slider}_words.csv',
                    mime='text/csv',
                )
            else:
                st.info(f"最大 {max_words_slider}単語の英語セグメントが見つかりませんでした。")

if __name__ == "__main__":
    main()