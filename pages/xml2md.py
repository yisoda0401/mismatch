# 必要なライブラリ
# pip install streamlit
import streamlit as st
import xml.etree.ElementTree as ET
import io
import os
import re
import zipfile

# ページの基本設定
st.set_page_config(page_title="DocBook XML to Markdown 変換ツール", layout="wide")
st.title("DocBook XML to Markdown 変換ツール")
st.subheader("DocBook 5.0形式のXMLファイルをMarkdown形式に変換")

# 名前空間の定義
NAMESPACES = {
    'db': 'http://docbook.org/ns/docbook',
    'xlink': 'http://www.w3.org/1999/xlink',
    'xi': 'http://www.w3.org/2001/XInclude'
}

# --- 変換ヘルパー関数 ---

def get_local_name(tag):
    """名前空間を除いたローカルタグ名を取得"""
    if '}' in tag:
        return tag.split('}')[1]
    return tag


def get_text_content(element):
    """
    要素からインライン装飾を処理してテキストを取得
    emphasis, literal, link などを適切なMarkdown記法に変換
    """
    if element is None:
        return ""
    
    result = []
    
    # 要素自体のテキスト
    if element.text:
        result.append(element.text)
    
    # 子要素を処理
    for child in element:
        local_name = get_local_name(child.tag)
        
        if local_name == 'emphasis':
            role = child.get('role', '')
            child_text = get_text_content(child)
            if role == 'strong':
                result.append(f"**{child_text}**")
            else:
                result.append(f"*{child_text}*")
        
        elif local_name == 'literal':
            child_text = get_text_content(child)
            result.append(f"`{child_text}`")
        
        elif local_name == 'link':
            href = child.get(f'{{{NAMESPACES["xlink"]}}}href', '')
            linkend = child.get('linkend', '')
            child_text = get_text_content(child)
            if href:
                result.append(f"[{child_text}]({href})")
            elif linkend:
                result.append(f"[{child_text}](#{linkend})")
            else:
                result.append(child_text)
        
        elif local_name == 'phrase':
            # phraseはそのまま内容を取得
            result.append(get_text_content(child))
        
        elif local_name == 'code':
            child_text = get_text_content(child)
            result.append(f"`{child_text}`")
        
        elif local_name == 'filename':
            child_text = get_text_content(child)
            result.append(f"`{child_text}`")
        
        elif local_name == 'command':
            child_text = get_text_content(child)
            result.append(f"`{child_text}`")
        
        elif local_name == 'replaceable':
            child_text = get_text_content(child)
            result.append(f"*{child_text}*")
        
        elif local_name == 'option':
            child_text = get_text_content(child)
            result.append(f"`{child_text}`")
        
        elif local_name == 'parameter':
            child_text = get_text_content(child)
            result.append(f"`{child_text}`")
        
        elif local_name == 'guimenu' or local_name == 'guibutton' or local_name == 'guilabel':
            child_text = get_text_content(child)
            result.append(f"**{child_text}**")
        
        else:
            # その他の要素は再帰的にテキストを取得
            result.append(get_text_content(child))
        
        # 子要素の後のテキスト（tail）
        if child.tail:
            result.append(child.tail)
    
    return ''.join(result)


def convert_code_block(element):
    """literallayout や screen をコードブロックに変換"""
    # 全テキストを取得（子要素含む）
    text_parts = []
    
    def extract_text(el):
        if el.text:
            text_parts.append(el.text)
        for child in el:
            extract_text(child)
            if child.tail:
                text_parts.append(child.tail)
    
    extract_text(element)
    code_text = ''.join(text_parts)
    
    # 前後の空白を整理
    code_text = code_text.strip()
    
    return f"\n```\n{code_text}\n```\n"


def convert_list(element, ordered=False, indent_level=0):
    """itemizedlist / orderedlist をMarkdownリストに変換"""
    result = []
    indent = "  " * indent_level
    counter = 1
    
    for child in element:
        local_name = get_local_name(child.tag)
        
        if local_name == 'title':
            # リストのタイトル
            title_text = get_text_content(child).strip()
            result.append(f"\n**{title_text}**\n")
        
        elif local_name == 'listitem':
            # リストアイテムの内容を取得
            item_content = []
            for item_child in child:
                item_local = get_local_name(item_child.tag)
                
                if item_local in ('simpara', 'para'):
                    text = get_text_content(item_child).strip()
                    if text:
                        item_content.append(text)
                
                elif item_local == 'itemizedlist':
                    # ネストされたリスト
                    nested = convert_list(item_child, ordered=False, indent_level=indent_level + 1)
                    item_content.append(nested)
                
                elif item_local == 'orderedlist':
                    nested = convert_list(item_child, ordered=True, indent_level=indent_level + 1)
                    item_content.append(nested)
                
                elif item_local in ('literallayout', 'screen'):
                    item_content.append(convert_code_block(item_child))
                
                else:
                    # その他の要素
                    text = get_text_content(item_child).strip()
                    if text:
                        item_content.append(text)
            
            if item_content:
                prefix = f"{counter}. " if ordered else "- "
                first_item = item_content[0] if item_content else ""
                result.append(f"{indent}{prefix}{first_item}")
                
                # 残りの内容（ネストされたリストなど）
                for rest in item_content[1:]:
                    if rest.strip().startswith("```") or rest.strip().startswith("-") or rest.strip().startswith("1."):
                        result.append(rest)
                    else:
                        result.append(f"{indent}  {rest}")
                
                counter += 1
    
    return '\n'.join(result)


def convert_variablelist(element):
    """variablelistを定義リスト風に変換"""
    result = []
    
    for child in element:
        local_name = get_local_name(child.tag)
        
        if local_name == 'title':
            title_text = get_text_content(child).strip()
            result.append(f"\n**{title_text}**\n")
        
        elif local_name == 'varlistentry':
            term = ""
            definition = ""
            
            for entry_child in child:
                entry_local = get_local_name(entry_child.tag)
                
                if entry_local == 'term':
                    term = get_text_content(entry_child).strip()
                
                elif entry_local == 'listitem':
                    def_parts = []
                    for li_child in entry_child:
                        li_local = get_local_name(li_child.tag)
                        if li_local in ('simpara', 'para'):
                            text = get_text_content(li_child).strip()
                            if text:
                                def_parts.append(text)
                        else:
                            text = get_text_content(li_child).strip()
                            if text:
                                def_parts.append(text)
                    definition = ' '.join(def_parts)
            
            if term:
                result.append(f"\n**{term}**")
                if definition:
                    result.append(f": {definition}")
    
    return '\n'.join(result)


def convert_admonition(element, admon_type):
    """note, important, warning をブロック引用に変換"""
    result = [f"\n> **{admon_type}:**"]
    
    for child in element:
        local_name = get_local_name(child.tag)
        
        if local_name == 'title':
            title_text = get_text_content(child).strip()
            result[0] = f"\n> **{title_text}:**"
        
        elif local_name in ('simpara', 'para'):
            text = get_text_content(child).strip()
            if text:
                result.append(f"> {text}")
        
        elif local_name == 'itemizedlist':
            list_md = convert_list(child, ordered=False)
            for line in list_md.split('\n'):
                if line.strip():
                    result.append(f"> {line}")
        
        elif local_name == 'orderedlist':
            list_md = convert_list(child, ordered=True)
            for line in list_md.split('\n'):
                if line.strip():
                    result.append(f"> {line}")
    
    result.append("")  # 空行を追加
    return '\n'.join(result)


def convert_figure(element):
    """figure / mediaobject を画像に変換"""
    result = []
    title = ""
    image_path = ""
    alt_text = ""
    
    for child in element:
        local_name = get_local_name(child.tag)
        
        if local_name == 'title':
            title = get_text_content(child)
        
        elif local_name == 'mediaobject':
            for media_child in child:
                media_local = get_local_name(media_child.tag)
                
                if media_local == 'imageobject':
                    for img_child in media_child:
                        img_local = get_local_name(img_child.tag)
                        if img_local == 'imagedata':
                            image_path = img_child.get('fileref', '')
                
                elif media_local == 'textobject':
                    for txt_child in media_child:
                        txt_local = get_local_name(txt_child.tag)
                        if txt_local == 'phrase':
                            alt_text = get_text_content(txt_child)
    
    if image_path:
        alt = alt_text if alt_text else title
        result.append(f"\n![{alt}]({image_path})")
        if title:
            result.append(f"*{title}*")
    
    return '\n'.join(result)


def convert_procedure(element):
    """procedure（手順）を順序付きリストに変換"""
    result = []
    step_num = 1
    
    for child in element:
        local_name = get_local_name(child.tag)
        
        if local_name == 'title':
            title_text = get_text_content(child)
            result.append(f"\n**{title_text}**\n")
        
        elif local_name == 'step':
            step_content = []
            for step_child in child:
                step_local = get_local_name(step_child.tag)
                
                if step_local in ('simpara', 'para'):
                    step_content.append(get_text_content(step_child))
                
                elif step_local in ('literallayout', 'screen'):
                    step_content.append(convert_code_block(step_child))
                
                elif step_local == 'itemizedlist':
                    step_content.append(convert_list(step_child, ordered=False, indent_level=1))
                
                elif step_local == 'orderedlist':
                    step_content.append(convert_list(step_child, ordered=True, indent_level=1))
            
            if step_content:
                result.append(f"{step_num}. {step_content[0]}")
                for rest in step_content[1:]:
                    result.append(f"   {rest}")
                step_num += 1
    
    return '\n'.join(result)


def convert_element(element, depth=0):
    """
    要素を再帰的にMarkdownに変換
    depth: 見出しレベル（1=章、2=セクション1、...）
    """
    if element is None:
        return ""
    
    result = []
    local_name = get_local_name(element.tag)
    
    # --- ドキュメント構造 ---
    if local_name == 'book':
        for child in element:
            result.append(convert_element(child, depth))
    
    elif local_name == 'info':
        # メタデータ
        for child in element:
            child_local = get_local_name(child.tag)
            
            if child_local == 'title':
                title_text = get_text_content(child).strip()
                result.append(f"# {title_text}\n")
            
            elif child_local == 'subtitle':
                subtitle_text = get_text_content(child).strip()
                result.append(f"*{subtitle_text}*\n")
            
            elif child_local == 'abstract':
                for abs_child in child:
                    abs_local = get_local_name(abs_child.tag)
                    if abs_local in ('simpara', 'para'):
                        text = get_text_content(abs_child).strip()
                        if text:
                            result.append(f"\n{text}\n")
            
            elif child_local == 'productname':
                product = get_text_content(child).strip()
                result.append(f"\n**Product:** {product}")
            
            elif child_local == 'productnumber':
                version = get_text_content(child).strip()
                result.append(f" {version}\n")
    
    elif local_name == 'chapter':
        chapter_id = element.get('{http://www.w3.org/XML/1998/namespace}id', '')
        for child in element:
            child_local = get_local_name(child.tag)
            
            if child_local == 'title':
                title_text = get_text_content(child)
                anchor = f" {{#{chapter_id}}}" if chapter_id else ""
                result.append(f"\n## {title_text}{anchor}\n")
            else:
                result.append(convert_element(child, depth=2))
    
    elif local_name == 'section':
        section_id = element.get('{http://www.w3.org/XML/1998/namespace}id', '')
        heading_level = min(depth + 1, 6)  # 最大h6まで
        heading_prefix = '#' * heading_level
        
        for child in element:
            child_local = get_local_name(child.tag)
            
            if child_local == 'title':
                title_text = get_text_content(child)
                anchor = f" {{#{section_id}}}" if section_id else ""
                result.append(f"\n{heading_prefix} {title_text}{anchor}\n")
            else:
                result.append(convert_element(child, depth=heading_level))
    
    # --- ブロック要素 ---
    elif local_name in ('simpara', 'para'):
        text = get_text_content(element).strip()
        if text:
            result.append(f"\n{text}\n")
    
    elif local_name == 'itemizedlist':
        result.append(f"\n{convert_list(element, ordered=False)}\n")
    
    elif local_name == 'orderedlist':
        result.append(f"\n{convert_list(element, ordered=True)}\n")
    
    elif local_name == 'variablelist':
        result.append(convert_variablelist(element))
    
    elif local_name in ('literallayout', 'screen'):
        result.append(convert_code_block(element))
    
    elif local_name == 'informalexample':
        for child in element:
            result.append(convert_element(child, depth))
    
    elif local_name == 'programlisting':
        result.append(convert_code_block(element))
    
    # --- アドモニション ---
    elif local_name == 'note':
        result.append(convert_admonition(element, "Note"))
    
    elif local_name == 'important':
        result.append(convert_admonition(element, "Important"))
    
    elif local_name == 'warning':
        result.append(convert_admonition(element, "Warning"))
    
    elif local_name == 'tip':
        result.append(convert_admonition(element, "Tip"))
    
    elif local_name == 'caution':
        result.append(convert_admonition(element, "Caution"))
    
    # --- 図表 ---
    elif local_name == 'figure':
        result.append(convert_figure(element))
    
    elif local_name == 'mediaobject':
        # figure外のmediaobject
        temp_fig = ET.Element('figure')
        temp_fig.append(element)
        result.append(convert_figure(temp_fig))
    
    # --- 手順 ---
    elif local_name == 'procedure':
        result.append(convert_procedure(element))
    
    # --- テーブル ---
    elif local_name == 'table' or local_name == 'informaltable':
        result.append(convert_table(element))
    
    # --- その他 ---
    elif local_name == 'bridgehead':
        # サブセクションのような見出し
        renderas = element.get('renderas', 'sect3')
        level = int(renderas[-1]) if renderas and renderas[-1].isdigit() else 3
        heading_prefix = '#' * min(level + 1, 6)
        text = get_text_content(element)
        result.append(f"\n{heading_prefix} {text}\n")
    
    elif local_name == 'formalpara':
        # タイトル付き段落
        for child in element:
            child_local = get_local_name(child.tag)
            if child_local == 'title':
                title_text = get_text_content(child)
                result.append(f"\n**{title_text}**\n")
            elif child_local in ('simpara', 'para'):
                text = get_text_content(child)
                result.append(f"{text}\n")
    
    elif local_name == 'blockquote':
        for child in element:
            child_local = get_local_name(child.tag)
            if child_local in ('simpara', 'para'):
                text = get_text_content(child)
                result.append(f"\n> {text}\n")
    
    else:
        # 未対応の要素は子要素を再帰処理
        for child in element:
            result.append(convert_element(child, depth))
    
    return ''.join(result)


def normalize_cell_text(text):
    """テーブルセル用にテキストを正規化（改行除去、空白整理）"""
    # 改行を空白に置換
    text = text.replace('\n', ' ').replace('\r', ' ')
    # 連続する空白を1つに
    text = re.sub(r'\s+', ' ', text)
    # 前後の空白を除去
    return text.strip()


def convert_table(element):
    """table / informaltable をMarkdownテーブルに変換"""
    result = []
    title = ""
    headers = []
    rows = []
    
    for child in element:
        local_name = get_local_name(child.tag)
        
        if local_name == 'title':
            title = normalize_cell_text(get_text_content(child))
        
        elif local_name == 'tgroup':
            for tg_child in child:
                tg_local = get_local_name(tg_child.tag)
                
                if tg_local == 'thead':
                    for row in tg_child:
                        if get_local_name(row.tag) == 'row':
                            header_row = []
                            for entry in row:
                                if get_local_name(entry.tag) == 'entry':
                                    cell_text = normalize_cell_text(get_text_content(entry))
                                    header_row.append(cell_text)
                            headers = header_row
                
                elif tg_local == 'tbody':
                    for row in tg_child:
                        if get_local_name(row.tag) == 'row':
                            data_row = []
                            for entry in row:
                                if get_local_name(entry.tag) == 'entry':
                                    cell_text = normalize_cell_text(get_text_content(entry))
                                    data_row.append(cell_text)
                            rows.append(data_row)
    
    if title:
        result.append(f"\n**{title}**\n")
    
    if headers:
        result.append("| " + " | ".join(headers) + " |")
        result.append("| " + " | ".join(["---"] * len(headers)) + " |")
    
    for row in rows:
        result.append("| " + " | ".join(row) + " |")
    
    result.append("")
    return '\n'.join(result)


def create_markdown_zip(converted_files):
    """
    変換済みファイルのリストからZIPを生成
    :param converted_files: [(filename, markdown_content), ...] のリスト
    :return: ZIPファイルのバイナリデータ
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for filename, content in converted_files:
            zip_file.writestr(filename, content.encode('utf-8'))
    return zip_buffer.getvalue()


def convert_xml_to_markdown(xml_content):
    """
    XMLコンテンツをMarkdownに変換するメイン関数
    """
    try:
        # XMLをパース（DTD検証をスキップ）
        # 外部エンティティを無視するために、DOCTYPE宣言を除去
        xml_str = xml_content.decode('utf-8') if isinstance(xml_content, bytes) else xml_content
        
        # DOCTYPE宣言を除去（外部エンティティ参照を避けるため）
        xml_str = re.sub(r'<!DOCTYPE[^>]*\[.*?\]>', '', xml_str, flags=re.DOTALL)
        xml_str = re.sub(r'<!DOCTYPE[^>]*>', '', xml_str)
        
        # パース
        root = ET.fromstring(xml_str)
        
        # 変換実行
        markdown = convert_element(root)
        
        # 整形：連続する空行を2行に制限
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        
        return markdown.strip()
    
    except ET.ParseError as e:
        raise ValueError(f"XMLパースエラー: {str(e)}")
    except Exception as e:
        raise ValueError(f"変換エラー: {str(e)}")


# --- メイン処理 ---

# ファイルアップローダー（複数ファイル対応）
uploaded_files = st.file_uploader(
    "DocBook XMLファイルをアップロード（複数選択可）",
    type=["xml"],
    accept_multiple_files=True
)

if uploaded_files:
    # 複数ファイルの変換処理
    converted_files = []  # [(filename.md, content), ...]
    errors = []  # [(filename, error_message), ...]
    
    with st.spinner("XMLファイルを変換中..."):
        for uploaded_file in uploaded_files:
            base_name = os.path.splitext(uploaded_file.name)[0]
            try:
                file_content = uploaded_file.read()
                markdown_content = convert_xml_to_markdown(file_content)
                converted_files.append((f"{base_name}.md", markdown_content))
            except ValueError as e:
                errors.append((uploaded_file.name, str(e)))
            except Exception as e:
                errors.append((uploaded_file.name, f"予期しないエラー: {str(e)}"))
    
    # 結果サマリーの表示
    total_files = len(uploaded_files)
    success_count = len(converted_files)
    error_count = len(errors)
    
    if success_count > 0:
        st.success(f"変換完了: {success_count}件成功 / {total_files}件中")
    
    if error_count > 0:
        st.warning(f"変換失敗: {error_count}件")
        with st.expander("エラー詳細"):
            for filename, error_msg in errors:
                st.error(f"**{filename}**: {error_msg}")
    
    # 変換成功したファイルがある場合
    if converted_files:
        st.divider()
        
        # --- ダウンロード ---
        st.subheader("ダウンロード")
        
        # ZIPファイルとしてダウンロード
        zip_data = create_markdown_zip(converted_files)
        st.download_button(
            label=f"ZIPファイルをダウンロード（{success_count}ファイル）",
            data=zip_data,
            file_name="converted_markdown.zip",
            mime="application/zip"
        )
        
        # 使い方セクション
        with st.expander("使い方"):
            st.markdown("""
            1. 上部の「Browse files」ボタンをクリックして、変換したいDocBook XMLファイル（`.xml`）をアップロードします。
               - 複数ファイルを同時に選択できます。
            2. 処理が完了すると、変換結果のサマリーが表示されます。
            3. 「ZIPファイルをダウンロード」ボタンをクリックして、変換結果をまとめてダウンロードします。
            4. 「表示するファイルを選択」ドロップダウンでファイルを選択し、プレビューを確認できます。
            """)

        with st.expander("対応要素"):
            st.markdown("""
            このツールは以下のDocBook 5.0要素に対応しています：
            
            **構造要素:**
            - `book`, `info`, `chapter`, `section`
            
            **ブロック要素:**
            - `simpara`, `para` - 段落
            - `itemizedlist`, `orderedlist` - リスト
            - `variablelist` - 定義リスト
            - `literallayout`, `screen`, `programlisting` - コードブロック
            - `table`, `informaltable` - テーブル
            - `figure`, `mediaobject` - 画像
            - `procedure` - 手順
            
            **インライン要素:**
            - `emphasis` - 強調（イタリック/太字）
            - `literal`, `code`, `filename`, `command` - コード
            - `link` - リンク
            
            **アドモニション:**
            - `note`, `important`, `warning`, `tip`, `caution`
            """)
        
        st.divider()
        
        # --- プレビュー ---
        st.subheader("プレビュー")
        
        # ファイル選択ドロップダウン
        file_options = [name for name, _ in converted_files]
        selected_file = st.selectbox("表示するファイルを選択", file_options)
        
        # 選択されたファイルの内容を取得
        selected_content = dict(converted_files)[selected_file]
        
        # タブでMarkdownソースとレンダリング結果を表示
        tab1, tab2 = st.tabs(["Markdownソース", "レンダリング結果"])
        
        with tab1:
            st.code(selected_content, language="markdown")
        
        with tab2:
            st.markdown(selected_content)

else:
    st.info("DocBook XMLファイルをアップロードして変換を開始してください。（複数ファイル選択可）")
