from __future__ import annotations

import csv
import base64
import hashlib
import html
import io
import json
import logging
import re
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup, NavigableString

try:
    import ebooklib
    from ebooklib import epub as ebooklib_epub
except Exception:  # pragma: no cover - optional dependency
    ebooklib = None
    ebooklib_epub = None

try:
    from cedict.cedict import DictionaryData, search as cedict_search
except Exception:  # pragma: no cover - optional dependency
    DictionaryData = None
    cedict_search = None

from epub_analyzer import (
    IELTS_TO_WORD_SIZE,
    analyze_epub_file,
    apply_known_words_to_analysis,
    load_known_words,
    load_spacy_model,
    normalize_word_form,
    parse_known_words_text,
    MAX_KNOWN_WORD_SIZE,
)


logger = logging.getLogger("bookvocab")

ANNOTATION_EXPORT_VERSION = 4


st.set_page_config(
    page_title="BookVocab APP",
    page_icon="📚",
    layout="wide",
    menu_items={
        "About": (
            "BookVocab Analyzer\n\n"
            "Made by hogo6002.\n\n"
            "Contributions are welcome.\n\n"
            "GitHub: https://github.com/hogo6002/BookVocab"
        ),
        "Get help": "https://github.com/hogo6002/BookVocab",
    },
)


TEXT = {
    "en": {
        "title": "BookVocab Analyzer",
        "subtitle": "Upload an EPUB, extract chapter text, review unknown words, and download an annotated EPUB.",
        "language": "Language",
        "sidebar_title": "Settings",
        "sidebar_caption": "Set your vocabulary size and cleanup filters here.",
        "sidebar_tip": "Use the sidebar to set language, vocabulary size, and cleanup filters.",
        "epub_file": "EPUB file",
        "vocab_basis": "Vocabulary basis",
        "vocab_mode_size": "Known vocabulary size",
        "known_vocab_size": "Known vocabulary size",
        "estimated_vocab_size": "Estimated vocabulary size",
        "cleanup_filters": "Cleanup filters",
        "remove_stopwords": "Remove stopwords",
        "remove_proper_nouns": "Remove proper nouns",
        "hide_no_defs": "Hide words without definitions",
        "hide_front_matter": "Hide front matter / non-chapters",
        "min_token_length": "Minimum token length",
        "optional_vocab": "Optional known-words list",
        "show_freq": "Show frequencies",
        "show_zh_definition": "Show Chinese dictionary definitions",
        "chinese_definition": "Chinese definition",
        "annotation_settings": "Annotation settings",
        "annotation_mode_inline": "Inline definition",
        "annotation_mode_endnote": "End-of-chapter notes",
        "upload_retry_hint": "If upload fails (for example, a 400 error), please try uploading again.",
        "reading_fit": "Reading fit",
        "reading_comfortable": "Comfortable reading",
        "reading_manageable": "Good learning material",
        "reading_difficult": "Challenging but usable",
        "reading_too_hard": "Too difficult",
        "reading_borderline": "Borderline for your case",
        "analyze": "Analyze EPUB",
        "chapter_mode_all": "All chapters",
        "chapter_mode_single": "Single chapter",
        "chapter_mode_range": "Chapter range",
        "all_chapters": "All chapters",
        "single_chapter": "Single chapter",
        "chapter_range": "Chapter range",
        "chapter_filter": "Chapter filter",
        "chapter": "Chapter",
        "start_chapter": "Start chapter",
        "end_chapter": "End chapter",
        "showing_full": "Showing the full book.",
        "range_help": "Set start and end to the same chapter for a single-chapter view, or extend end to include later chapters.",
        "filter_words": "Filter words",
        "selectable_words": "Copyable word list",
        "download_anki": "Download Anki TSV",
        "download_annotated_epub": "Download annotated EPUB",
        "download_annotated_epub_direct_link": "Click here to download directly.",
        "download_annotated_epub_direct_hint": "If the button still fails, use this direct link:",
        "prepare_annotated_epub": "Prepare annotated EPUB",
        "unique_words": "Unique words",
        "chapters": "Chapters",
        "unique_unknown_words": "Unique unknown words",
        "known_source": "Known words source",
        "visible_filters": "Visible after current filters",
        "dict_defs": "Definitions found for",
        "word": "Word",
        "definition": "Definition",
        "frequency": "Freq",
        "context": "Context",
        "book_order_note": "Words are listed in the order they appear in the book.",
        "row_hint": "Click the left side of a row to see the sentence context below.",
    },
    "zh": {
        "title": "轻松看懂英文书",
        "subtitle": "上传 EPUB，提取章节文本，查看不认识的单词和释义，并下载带释义 EPUB。",
        "language": "语言",
        "sidebar_title": "设置",
        "sidebar_caption": "在这里设置词汇量和清理过滤器。",
        "sidebar_tip": "请在侧边栏中设置语言、词汇量和清理过滤器。",
        "epub_file": "EPUB 文件",
        "vocab_basis": "词汇基准",
        "vocab_mode_size": "已知词汇量",
        "known_vocab_size": "已知词汇量",
        "estimated_vocab_size": "估计词汇量",
        "cleanup_filters": "清理过滤器",
        "remove_stopwords": "移除停用词",
        "remove_proper_nouns": "移除专有名词",
        "hide_no_defs": "隐藏无释义词",
        "hide_front_matter": "隐藏前言 / 非正文",
        "min_token_length": "最小词长",
        "optional_vocab": "可选已知词表",
        "show_freq": "显示频率",
        "show_zh_definition": "显示中文词典释义",
        "chinese_definition": "中文释义",
        "annotation_settings": "注释设置",
        "annotation_mode_inline": "行内释义",
        "annotation_mode_endnote": "章节末尾注释",
        "upload_retry_hint": "如果上传失败（例如 400 错误），请重新上传一次。",
        "reading_fit": "阅读适配",
        "reading_comfortable": "轻松阅读",
        "reading_manageable": "适合学习",
        "reading_difficult": "有点难但能读",
        "reading_too_hard": "太难",
        "reading_borderline": "接近你的阅读情况",
        "analyze": "分析 EPUB",
        "chapter_mode_all": "全部章节",
        "chapter_mode_single": "单章",
        "chapter_mode_range": "章节范围",
        "all_chapters": "全部章节",
        "single_chapter": "单章",
        "chapter_range": "章节范围",
        "chapter_filter": "章节筛选",
        "chapter": "章节",
        "start_chapter": "起始章节",
        "end_chapter": "结束章节",
        "showing_full": "当前显示整本书。",
        "range_help": "把起始和结束设成同一章就是单章视图；把结束章往后调就是章节范围。",
        "filter_words": "筛选单词",
        "selectable_words": "可复制单词列表",
        "download_anki": "下载 Anki TSV",
        "download_annotated_epub": "下载带释义 EPUB",
        "download_annotated_epub_direct_link": "点这里直接下载。",
        "download_annotated_epub_direct_hint": "如果按钮仍然下载失败，请使用这个直接链接：",
        "prepare_annotated_epub": "生成带释义 EPUB",
        "unique_words": "唯一词数",
        "chapters": "章节数",
        "unique_unknown_words": "生词数",
        "known_source": "已知词来源",
        "visible_filters": "当前过滤后可见",
        "dict_defs": "有释义的生词数为",
        "word": "单词",
        "definition": "释义",
        "frequency": "频率",
        "context": "上下文",
        "book_order_note": "单词按在书中出现的顺序显示。",
        "row_hint": "点击每行最左侧即可在下方查看上下文。",
    },
}

LANG_LABELS = {
    "en": "English",
    "zh": "中文",
}


def t(key: str) -> str:
    lang = st.session_state.get("ui_lang", current_lang)
    return TEXT.get(lang, TEXT["en"]).get(key, TEXT["en"].get(key, key))


def choice_label(key: str) -> str:
    return t(key)


def detect_browser_language() -> str:
    try:
        accept_language = st.context.headers.get("accept-language", "")
    except Exception:
        accept_language = ""
    return "zh" if "zh" in accept_language.lower() else "en"


current_lang = st.session_state.get("ui_lang", detect_browser_language())


def approximate_level_label(size: int) -> str:
    if size < 1500:
        cefr, ielts, label = "A1", "1.0 - 2.5", "Beginner"
        zh_label = "入门"
    elif size < 3000:
        cefr, ielts, label = "A2", "3.0 - 3.5", "Elementary"
        zh_label = "初级"
    elif size < 5000:
        cefr, ielts, label = "B1", "4.0 - 5.0", "Intermediate"
        zh_label = "中级"
    elif size < 8000:
        cefr, ielts, label = "B2", "5.5 - 6.5", "Upper-Intermediate"
        zh_label = "中上级"
    elif size <= 12000:
        cefr, ielts, label = "C1", "7.0 - 8.0", "Advanced"
        zh_label = "高级"
    else:
        cefr, ielts, label = "C2", "8.5 - 9.0", "Proficiency"
        zh_label = "精通"

    if current_lang == "en":
        return f"roughly {label} · {cefr} · IELTS {ielts}"
    return f"约{zh_label} · {cefr} · IELTS {ielts}"


def reading_fit_from_coverage(coverage: float) -> str:
    if coverage >= 0.98:
        return "Fluent reading"
    if coverage >= 0.95:
        return "Good learning material"
    if coverage >= 0.90:
        return "Challenging but usable"
    return "Too difficult"


def reading_fit_color(coverage: float) -> str:
    if coverage >= 0.98:
        return "#1a7f37"
    if coverage >= 0.95:
        return "#2f6fdf"
    if coverage >= 0.90:
        return "#b26a00"
    return "#c62828"


def localized_reading_fit(coverage: float) -> str:
    if coverage >= 0.98:
        return t("reading_comfortable")
    if coverage >= 0.95:
        return t("reading_manageable")
    if coverage >= 0.90:
        return t("reading_difficult")
    return t("reading_too_hard")


@st.cache_resource(show_spinner=False)
def load_cedict_dictionary():
    if DictionaryData is None:
        return None
    try:
        return DictionaryData()
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def translate_word_to_zh(word: str) -> str:
    word = word.strip().lower()
    if not word or cedict_search is None:
        return ""
    dictionary = load_cedict_dictionary()
    if dictionary is None:
        return ""
    try:
        result = cedict_search(word, dictionary)
    except Exception:
        return ""
    if isinstance(result, str):
        return result.strip()
    if isinstance(result, tuple):
        for item in reversed(result):
            if isinstance(item, str) and item.strip():
                return item.strip()
    if isinstance(result, list):
        for item in result:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return ""


def store_uploaded_file(
    uploaded_file, *, bytes_key: str, name_key: str, hash_key: str
) -> bytes:
    data = uploaded_file.getvalue()
    st.session_state[bytes_key] = data
    st.session_state[name_key] = uploaded_file.name
    st.session_state[hash_key] = hashlib.sha256(data).hexdigest()
    return data


def analysis_input_config(
    epub_hash: str | None,
    remove_stopwords: bool,
    remove_proper_nouns: bool,
    min_token_length: int,
) -> dict:
    return {
        "upload_hash": epub_hash,
        "remove_stopwords": remove_stopwords,
        "remove_proper_nouns": remove_proper_nouns,
        "min_token_length": min_token_length,
    }


@st.cache_data(show_spinner=False)
def analyze_epub_bytes_cached(
    epub_bytes: bytes,
    epub_name: str,
    remove_stopwords: bool,
    remove_proper_nouns: bool,
    min_token_length: int,
) -> dict:
    suffix = Path(epub_name).suffix or ".epub"
    if suffix.lower() == ".zip":
        suffix = ".epub"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(epub_bytes)
        tmp_path = Path(tmp.name)
    try:
        result = analyze_epub_file(
            tmp_path,
            known_words=set(),
            remove_stopwords=remove_stopwords,
            remove_proper_nouns=remove_proper_nouns,
            min_token_length=min_token_length,
            known_words_source="raw parse",
        )
        return result.to_dict()
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


@st.cache_data(show_spinner=False)
def build_anki_tsv(
    result: dict, *, use_chinese_definition: bool, hide_undefined_words: bool
) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter="\t")
    writer.writerow(["word", "definition", "chapter", "freq"])
    seen: set[tuple[str, str]] = set()
    for chapter in result["chapters"]:
        chapter_name = chapter_short_name(chapter)
        for row in chapter["oov_words"]:
            definition = row.get("definition", "")
            if use_chinese_definition:
                definition = translate_word_to_zh(row["word"]) or definition
            if hide_undefined_words and not definition.strip():
                continue
            key = (row["word"], definition)
            if key in seen:
                continue
            seen.add(key)
            writer.writerow(
                [
                    row["word"],
                    definition,
                    chapter_name,
                    row.get("freq", ""),
                ]
            )
    return buffer.getvalue()


def export_text_payload(text: str) -> bytes:
    return text.encode("utf-8")


def annotated_epub_download_name(source_name: str | None) -> str:
    stem = Path(source_name or "").stem.strip() or "Book"
    return f"{stem} (BookVocab version).epub"


def render_direct_download_link(
    *,
    label: str,
    data: bytes,
    file_name: str,
    mime: str,
) -> None:
    encoded = base64.b64encode(data).decode("ascii")
    safe_label = html.escape(label)
    safe_name = html.escape(file_name, quote=True)
    st.markdown(
        (
            f'<a download="{safe_name}" '
            f'href="data:{mime};base64,{encoded}" '
            f'style="text-decoration:underline;">{safe_label}</a>'
        ),
        unsafe_allow_html=True,
    )


def format_annotation_definition_text(
    en_definition: str, zh_definition: str, mode: str, show_chinese_definitions: bool
) -> str:
    en_text = (en_definition or "").strip()
    zh_text = (zh_definition or "").strip()

    if not show_chinese_definitions:
        return en_text
    if mode == "inline":
        return zh_text or en_text
    if mode == "endnote":
        if en_text and zh_text:
            return f"{en_text} | {zh_text}"
        return en_text or zh_text
    return en_text or zh_text


def chapter_definition_map(
    chapter: dict,
    *,
    show_chinese_definitions: bool,
    zh_definition_map: dict[str, str] | None = None,
) -> dict[str, dict[str, str]]:
    mapping: dict[str, dict[str, str]] = {}
    need_zh = show_chinese_definitions
    for row in chapter.get("oov_words", []):
        word = row.get("word", "").strip().lower()
        if not word:
            continue

        en_definition = (row.get("definition", "") or "").strip()
        if need_zh:
            if zh_definition_map is not None:
                zh_definition = (zh_definition_map.get(word, "") or "").strip()
            else:
                zh_definition = translate_word_to_zh(word).strip()
        else:
            zh_definition = ""
        inline_definition = format_annotation_definition_text(
            en_definition,
            zh_definition,
            mode="inline",
            show_chinese_definitions=show_chinese_definitions,
        )
        endnote_definition = format_annotation_definition_text(
            en_definition,
            zh_definition,
            mode="endnote",
            show_chinese_definitions=show_chinese_definitions,
        )
        if not inline_definition and not endnote_definition:
            continue

        mapping[word] = {
            "inline": inline_definition,
            "endnote": endnote_definition,
        }
    return mapping


ANNOTATION_SKIP_TAGS = {
    "a",
    "code",
    "head",
    "link",
    "math",
    "meta",
    "nav",
    "noscript",
    "ol",
    "pre",
    "script",
    "style",
    "sub",
    "sup",
    "ul",
    "li",
    "svg",
    "textarea",
    "title",
}

NOTE_RELATED_HINTS = ("noteref", "footnote", "endnote", "rearnote", "annotation")


def _is_note_related_element(tag) -> bool:
    if tag is None:
        return False
    epub_type = str(tag.get("epub:type", "") or "").lower()
    role = str(tag.get("role", "") or "").lower()
    element_id = str(tag.get("id", "") or "").lower()
    classes = tag.get("class", []) or []
    if isinstance(classes, str):
        classes = [classes]
    class_text = " ".join(str(item).lower() for item in classes)

    searchable = [epub_type, role, element_id, class_text]
    return any(hint in value for value in searchable for hint in NOTE_RELATED_HINTS)


def _normalize_existing_note_links(soup: BeautifulSoup) -> None:
    # Preserve source-book note behavior as plain jump links.
    for anchor in soup.find_all("a"):
        epub_type = str(anchor.get("epub:type", "") or "").lower()
        role = str(anchor.get("role", "") or "").lower()
        is_note_ref = "noteref" in epub_type or "doc-noteref" in role
        if not is_note_ref:
            continue
        for attr in ("epub:type", "role", "title", "data-footnote", "data-note"):
            if anchor.has_attr(attr):
                del anchor[attr]


def _should_skip_annotation_node(node: NavigableString) -> bool:
    if not str(node).strip():
        return True
    for ancestor in node.parents:
        name = getattr(ancestor, "name", "")
        if not name:
            continue
        if name.lower() in ANNOTATION_SKIP_TAGS:
            return True
        if _is_note_related_element(ancestor):
            return True
        classes = getattr(ancestor, "get", lambda *_: [])("class", []) or []
        if isinstance(classes, str):
            classes = [classes]
        if (
            "bookvocab-note" in classes
            or "bookvocab-note-gloss" in classes
            or "bookvocab-note-term" in classes
            or "bookvocab-note-ref" in classes
            or "bookvocab-note-inline" in classes
            or "bookvocab-notes" in classes
        ):
            return True
    return False


def _annotate_text_fragment_for_epub(
    text: str,
    *,
    definitions: dict[str, dict[str, str]],
    show_inline: bool,
    show_endnote: bool,
    seen_words: set[str],
    notes: list[dict[str, str]],
    nlp,
) -> tuple[str, bool]:
    doc = nlp(text)
    parts: list[str] = []
    changed = False

    for token in doc:
        if token.is_space:
            parts.append(html.escape(token.text_with_ws))
            continue
        if token.is_stop or token.pos_ == "PROPN":
            parts.append(html.escape(token.text_with_ws))
            continue

        lemma = (
            token.lemma_ if token.lemma_ and token.lemma_ != "-PRON-" else token.text
        )
        normalized = normalize_word_form(lemma)
        definition_entry = definitions.get(normalized, {})
        inline_gloss = (definition_entry.get("inline", "") or "").strip()
        endnote_gloss = (definition_entry.get("endnote", "") or "").strip()
        if (not inline_gloss and not endnote_gloss) or normalized in seen_words:
            parts.append(html.escape(token.text_with_ws))
            continue

        token_text = html.escape(token.text)
        token_ws = html.escape(token.whitespace_)
        term_html = (
            '<span class="bookvocab-note-term" '
            'style="text-decoration:underline;text-decoration-style:dotted;'
            'text-decoration-color:#b45309;">'
            f"{token_text}</span>"
        )

        marker_html = ""
        if show_endnote and endnote_gloss:
            note_number = len(notes) + 1
            note_id = f"bookvocab-note-{note_number}"
            ref_id = f"bookvocab-note-ref-{note_number}"
            marker_html = (
                f'<sup class="bookvocab-note-ref" id="{ref_id}" '
                'style="font-size:0.72em;vertical-align:super;line-height:0;'
                'margin-left:0.08em;">'
                f'<a href="#{note_id}"'
                ' style="text-decoration:none;color:#8a5a00;">'
                f"{note_number}</a></sup>"
            )
            notes.append(
                {
                    "note_id": note_id,
                    "ref_id": ref_id,
                    "word": token.text,
                    "gloss": endnote_gloss,
                }
            )

        inline_html = ""
        if show_inline and inline_gloss:
            inline_html = (
                '<span class="bookvocab-note-inline" '
                'style="font-size:0.78em;color:#6b4e16;margin-left:0.25em;">'
                f"{html.escape(inline_gloss)}"
                "</span>"
            )

        parts.append(f"{term_html}{marker_html}{inline_html}{token_ws}")
        seen_words.add(normalized)
        changed = True

    return "".join(parts), changed


def _append_epub_notes_section(soup: BeautifulSoup, notes: list[dict[str, str]]) -> None:
    if not notes:
        return

    body = soup.find("body")
    if body is None:
        body = soup

    section = soup.new_tag(
        "section",
        attrs={
            "class": "bookvocab-notes",
            "style": "margin-top:1.2em;padding-top:0.8em;border-top:1px solid #d8d8d8;",
        },
    )
    heading = soup.new_tag(
        "p",
        attrs={"style": "margin:0 0 0.5em 0;font-weight:600;color:#6b4e16;"},
    )
    heading.string = "Vocabulary Notes / 注释"
    section.append(heading)

    ordered = soup.new_tag("ol", attrs={"style": "margin:0;padding-left:1.25em;"})
    for note in notes:
        item = soup.new_tag(
            "li",
            attrs={"id": note["note_id"], "style": "margin:0 0 0.35em 0;"},
        )
        word = soup.new_tag("strong")
        word.string = note["word"]
        item.append(word)
        item.append(": ")
        item.append(note["gloss"])
        item.append(" ")
        back = soup.new_tag(
            "a",
            href=f"#{note['ref_id']}",
            attrs={"style": "text-decoration:none;color:#8a5a00;"},
        )
        back.string = "↩"
        item.append(back)
        ordered.append(item)
    section.append(ordered)
    body.append(section)


def annotate_html_for_epub(
    html_content: bytes | str,
    *,
    definitions: dict[str, dict[str, str]],
    show_inline_annotation: bool,
    show_endnote_annotation: bool,
    nlp,
) -> bytes:
    if html_content is None:
        source_html = ""
    else:
        source_html = (
            html_content.decode("utf-8", errors="ignore")
            if isinstance(html_content, bytes)
            else str(html_content)
        )
    if not source_html or not definitions:
        return source_html.encode("utf-8")

    try:
        if not show_inline_annotation and not show_endnote_annotation:
            return source_html.encode("utf-8")
        soup = BeautifulSoup(source_html, "html.parser")
        _normalize_existing_note_links(soup)
        seen_words: set[str] = set()
        notes: list[dict[str, str]] = []
        text_nodes = [
            node
            for node in soup.find_all(string=True)
            if isinstance(node, NavigableString) and not _should_skip_annotation_node(node)
        ]
        for text_node in text_nodes:
            annotated_html, changed = _annotate_text_fragment_for_epub(
                str(text_node),
                definitions=definitions,
                show_inline=show_inline_annotation,
                show_endnote=show_endnote_annotation,
                seen_words=seen_words,
                notes=notes,
                nlp=nlp,
            )
            if not changed:
                continue
            fragment = BeautifulSoup(annotated_html, "html.parser")
            replacement_nodes = list(fragment.contents)
            if not replacement_nodes:
                continue
            for replacement in reversed(replacement_nodes):
                text_node.insert_after(replacement)
            text_node.extract()
        if show_endnote_annotation:
            _append_epub_notes_section(soup, notes)
        return str(soup).encode("utf-8")
    except Exception:
        return source_html.encode("utf-8")


def build_annotated_epub_bytes(
    result: dict,
    *,
    source_epub_bytes: bytes,
    source_epub_name: str,
    show_inline_annotation: bool,
    show_endnote_annotation: bool,
    show_chinese_definitions: bool,
    progress_bar=None,
) -> bytes:
    if ebooklib_epub is None:
        raise RuntimeError("ebooklib is not installed.")

    suffix = Path(source_epub_name).suffix or ".epub"
    if suffix.lower() == ".zip":
        suffix = ".epub"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(source_epub_bytes)
        tmp_path = Path(tmp.name)

    try:
        book = ebooklib_epub.read_epub(str(tmp_path))
        chapter_results = result.get("chapters", [])
        document_items = [
            item for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)
        ]
        zh_definition_map: dict[str, str] | None = None
        if show_chinese_definitions:
            unique_words = {
                (row.get("word", "") or "").strip().lower()
                for chapter in chapter_results
                for row in chapter.get("oov_words", [])
                if (row.get("word", "") or "").strip()
            }
            zh_definition_map = {
                word: translate_word_to_zh(word)
                for word in unique_words
            }
        nlp = load_spacy_model()
        for chapter_index, (chapter, item) in enumerate(
            zip(chapter_results, document_items), start=1
        ):
            defs = chapter_definition_map(
                chapter,
                show_chinese_definitions=show_chinese_definitions,
                zh_definition_map=zh_definition_map,
            )
            item.content = annotate_html_for_epub(
                item.get_content(),
                definitions=defs,
                show_inline_annotation=show_inline_annotation,
                show_endnote_annotation=show_endnote_annotation,
                nlp=nlp,
            )
            if progress_bar is not None:
                total = max(min(len(chapter_results), len(document_items)), 1)
                progress_bar.progress(min(chapter_index / total, 1.0))
        existing_ids = {
            str(
                (
                    item.get_id()
                    if callable(getattr(item, "get_id", None))
                    else getattr(item, "id", "")
                )
                or ""
            ).lower()
            for item in book.get_items()
        }
        has_ncx = "ncx" in existing_ids or any(
            str(getattr(item, "file_name", "") or "").lower().endswith(".ncx")
            for item in book.get_items()
        )
        has_nav = "nav" in existing_ids or any(
            "nav" in (getattr(item, "properties", []) or [])
            for item in book.get_items()
        )
        if not has_ncx:
            book.add_item(ebooklib_epub.EpubNcx())
        if not has_nav:
            book.add_item(ebooklib_epub.EpubNav())
        out = tempfile.NamedTemporaryFile(delete=False, suffix=".epub")
        out_path = Path(out.name)
        out.close()
        try:
            ebooklib_epub.write_epub(str(out_path), book)
            return out_path.read_bytes()
        finally:
            try:
                out_path.unlink(missing_ok=True)
            except Exception:
                pass
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def flatten_oov_rows(chapters: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for chapter_order, chapter in enumerate(chapters, start=1):
        title = chapter_short_name(chapter)
        for row in chapter["oov_words"]:
            rows.append(
                {
                    "chapter": title,
                    "word": row["word"],
                    "freq": row.get("freq", 0),
                    "definition": row.get("definition", ""),
                    "context": row.get("context", ""),
                    "_chapter_order": chapter_order,
                }
            )
    return rows


def chapter_display_name(chapter: dict) -> str:
    title = (chapter.get("title") or "").strip()
    chapter_id = chapter.get("chapter_id", "")
    if not title or title.lower().endswith(".xhtml"):
        return chapter_id.replace("chapter_", "Chapter ")
    return title


def chapter_short_name(chapter: dict) -> str:
    chapter_id = chapter.get("chapter_id", "")
    title = (chapter.get("title") or "").strip()
    if not title or title.lower().endswith(".xhtml"):
        return chapter_id.replace("chapter_", "Chapter ")
    return title


FRONT_MATTER_PATTERNS = (
    "cover",
    "title page",
    "copyright",
    "contents",
    "table of contents",
    "author's note",
    "authors note",
    "a note on the text",
    "acknowledg",
    "dedication",
    "preface",
    "foreword",
    "prologue",
    "about the author",
    "imprint",
)


def is_front_matter(chapter: dict) -> bool:
    title = chapter_short_name(chapter).lower()
    return any(pattern in title for pattern in FRONT_MATTER_PATTERNS)


def extract_chapter_number(title: str) -> str | None:
    match = re.search(r"\bchapter\s+([0-9]+|[ivxlcdm]+)\b", title, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper()
    match = re.search(
        r"\bch(?:apter)?\.?\s*([0-9]+|[ivxlcdm]+)\b", title, flags=re.IGNORECASE
    )
    if match:
        return match.group(1).upper()
    return None


def chapter_index(chapter: dict) -> int:
    chapter_id = chapter.get("chapter_id", "chapter_0")
    try:
        return int(chapter_id.split("_", 1)[1])
    except Exception:
        return 0


def chapter_label(
    chapter: dict, hide_undefined_words: bool, use_chinese_definition: bool = False
) -> str:
    if hide_undefined_words and not use_chinese_definition:
        count = sum(
            1
            for row in chapter.get("oov_words", [])
            if row.get("definition", "").strip()
        )
    else:
        count = len(chapter.get("oov_words", []))
    title = chapter_short_name(chapter)
    number = extract_chapter_number(title)
    if title.lower().startswith("chapter "):
        return f"{title} ({count})"
    if number:
        return f"Chapter {number} · {title} ({count})"
    return f"{title} ({count})"


def chapter_window(
    chapters: list[dict], start_index: int, end_index: int
) -> list[dict]:
    try:
        return chapters[start_index : end_index + 1]
    except Exception:
        return chapters


def chapter_has_visible_oov(
    chapter: dict, hide_undefined_words: bool, use_chinese_definition: bool = False
) -> bool:
    if hide_undefined_words and not use_chinese_definition:
        return any(
            row.get("definition", "").strip() for row in chapter.get("oov_words", [])
        )
    return bool(chapter.get("oov_words", []))


def selection_row_index(table_event) -> int | None:
    if table_event is None:
        return None
    selection = getattr(table_event, "selection", None)
    if selection is None and isinstance(table_event, dict):
        selection = table_event.get("selection")
    if selection is None:
        return None
    rows = getattr(selection, "rows", None)
    if rows is None and isinstance(selection, dict):
        rows = selection.get("rows")
    if not rows:
        return None
    try:
        return int(rows[0])
    except Exception:
        return None


def friendly_failure_message(action: str, exc: Exception) -> str:
    logger.exception("%s failed", action)
    if st.session_state.get("ui_lang", "en") == "en":
        return (
            f"{action} failed: {exc}. "
            "If this happened during upload or download, please try again; "
            "it is usually a transient browser or network issue."
        )
    return (
        f"{action}失败：{exc}。"
        "如果发生在上传或下载时，请再试一次；通常是浏览器或网络的临时问题。"
    )


def show_status_toast(message_en: str, message_zh: str) -> None:
    toast = getattr(st, "toast", None)
    if toast is None:
        return
    toast(message_en if st.session_state.get("ui_lang", "en") == "en" else message_zh)


st.header(t("title"))
st.caption(t("subtitle"))
st.info(t("sidebar_tip"))

st.radio(
    t("language"),
    ["en", "zh"],
    index=0 if current_lang == "en" else 1,
    format_func=lambda value: LANG_LABELS.get(value, value),
    key="ui_lang",
    horizontal=True,
)
ui_lang = st.session_state.get("ui_lang", current_lang)

uploaded_epub = st.file_uploader(
    t("epub_file"), type=["epub", "zip"], key="epub_upload"
)
uploaded_epub_bytes = None
uploaded_epub_name = None
uploaded_epub_hash = None
if uploaded_epub is not None:
    uploaded_epub_bytes = store_uploaded_file(
        uploaded_epub,
        bytes_key="uploaded_epub_bytes",
        name_key="uploaded_epub_name",
        hash_key="uploaded_epub_hash",
    )
    uploaded_epub_name = uploaded_epub.name
    uploaded_epub_hash = st.session_state.get("uploaded_epub_hash")
else:
    uploaded_epub_bytes = st.session_state.get("uploaded_epub_bytes")
    uploaded_epub_name = st.session_state.get("uploaded_epub_name")
    uploaded_epub_hash = st.session_state.get("uploaded_epub_hash")

with st.sidebar:
    st.header(t("sidebar_title"))
    st.caption(t("sidebar_caption"))
    vocab_size = st.slider(
        t("estimated_vocab_size"),
        1000,
        MAX_KNOWN_WORD_SIZE,
        value=12000,
        step=1000,
    )
    st.caption(
        f"{t('estimated_vocab_size')}: {vocab_size:,} ({approximate_level_label(vocab_size)})"
    )
    st.markdown(f"**{t('cleanup_filters')}**")
    remove_stopwords = st.checkbox(t("remove_stopwords"), value=True)
    remove_proper_nouns = st.checkbox(t("remove_proper_nouns"), value=True)
    hide_undefined_words = st.checkbox(t("hide_no_defs"), value=True)
    if "show_inline_annotation" not in st.session_state:
        st.session_state["show_inline_annotation"] = True
    if "show_endnote_annotation" not in st.session_state:
        st.session_state["show_endnote_annotation"] = True
    previous_lang = st.session_state.get("_last_ui_lang")
    if previous_lang is not None and previous_lang != ui_lang:
        st.session_state["show_inline_annotation"] = True
        st.session_state["show_endnote_annotation"] = True
    if "show_zh_definition" not in st.session_state:
        st.session_state["show_zh_definition"] = ui_lang == "zh"
    elif ui_lang == "zh" and previous_lang != "zh":
        st.session_state["show_zh_definition"] = True
    show_chinese_definitions = st.checkbox(t("show_zh_definition"), key="show_zh_definition")
    st.session_state["_last_ui_lang"] = ui_lang
    hide_front_matter = st.checkbox(t("hide_front_matter"), value=False)
    show_frequencies = st.checkbox(t("show_freq"), value=False)
    st.markdown("<div style='margin-top:0.5rem;'></div>", unsafe_allow_html=True)
    st.markdown(f"**{t('annotation_settings')}**")
    show_inline_annotation = st.checkbox(
        t("annotation_mode_inline"), key="show_inline_annotation"
    )
    show_endnote_annotation = st.checkbox(
        t("annotation_mode_endnote"), key="show_endnote_annotation"
    )
    st.markdown("<div style='margin-top:0.35rem;'></div>", unsafe_allow_html=True)
    min_token_length = 3
    custom_vocab = st.file_uploader(
        t("optional_vocab"), type=["txt", "csv"], key="vocab"
    )
    custom_vocab_text = None
    if custom_vocab is not None:
        custom_vocab_text = custom_vocab.getvalue().decode("utf-8", errors="ignore")
        st.session_state["custom_vocab_text"] = custom_vocab_text
        st.session_state["custom_vocab_name"] = custom_vocab.name
    else:
        custom_vocab_text = st.session_state.get("custom_vocab_text")
analysis_result: dict | None = None
analysis_meta: dict | None = None

current_input_config = analysis_input_config(
    uploaded_epub_hash,
    remove_stopwords,
    remove_proper_nouns,
    min_token_length,
)

stored = st.session_state.get("analysis_result")
stored_input_config = st.session_state.get("analysis_input_config")

active_epub_bytes = uploaded_epub_bytes
active_epub_name = uploaded_epub_name

if not (active_epub_bytes and active_epub_name):
    st.caption(t("upload_retry_hint"))

if active_epub_bytes and active_epub_name:
    if st.button(t("analyze"), type="primary"):
        try:
            with st.spinner(
                "Analyzing chapters..."
                if st.session_state.get("ui_lang", "en") == "en"
                else "正在分析章节..."
            ):
                analysis_result = analyze_epub_bytes_cached(
                    active_epub_bytes,
                    active_epub_name,
                    remove_stopwords,
                    remove_proper_nouns,
                    min_token_length,
                )
        except Exception as exc:
            st.error(friendly_failure_message("Analysis", exc))
        else:
            st.session_state["analysis_input_config"] = current_input_config
            st.session_state["analysis_result"] = analysis_result
            st.session_state["analysis_meta"] = {
                "vocab_size": vocab_size,
                "known_words_source": "",
            }
            st.session_state["uploaded_epub_bytes"] = active_epub_bytes
            st.session_state["uploaded_epub_name"] = active_epub_name
            st.session_state["uploaded_epub_hash"] = uploaded_epub_hash
            st.session_state["custom_vocab_text"] = custom_vocab_text
            analysis_meta = st.session_state["analysis_meta"]
if active_epub_bytes and active_epub_name:
    if stored and stored_input_config == current_input_config:
        analysis_meta = st.session_state.get("analysis_meta")
        analysis_result = stored
    elif stored and stored_input_config != current_input_config:
        st.info(
            "Current file or text settings differ from the last analysis. Re-running on the loaded EPUB."
            if st.session_state.get("ui_lang", "en") == "en"
            else "当前文件或文本设置与上次分析不同。正在基于已加载的 EPUB 重新分析。"
        )
        try:
            with st.spinner(
                "Analyzing chapters..."
                if st.session_state.get("ui_lang", "en") == "en"
                else "正在分析章节..."
            ):
                analysis_result = analyze_epub_bytes_cached(
                    active_epub_bytes,
                    active_epub_name,
                    remove_stopwords,
                    remove_proper_nouns,
                    min_token_length,
                )
        except Exception as exc:
            st.error(friendly_failure_message("Analysis", exc))
        else:
            analysis_meta = st.session_state.get("analysis_meta")
            analysis_result["known_words_source"] = ""
            st.session_state["analysis_input_config"] = current_input_config
            st.session_state["analysis_result"] = analysis_result

if analysis_result:
    if not analysis_result["chapters"]:
        st.warning(
            "No chapter documents were found in this EPUB."
            if st.session_state.get("ui_lang", "en") == "en"
            else "这个 EPUB 没有找到章节内容。"
        )
        st.stop()

    if custom_vocab_text:
        custom_words = parse_known_words_text(custom_vocab_text)
        known_words, known_words_source = load_known_words(custom_words=custom_words)
    else:
        known_words, known_words_source = load_known_words(
            size=vocab_size,
        )

    analysis_result = apply_known_words_to_analysis(analysis_result, known_words)
    analysis_result["known_words_source"] = known_words_source
    analysis_meta = {
        "vocab_size": vocab_size,
        "known_words_source": known_words_source,
    }

    visible_chapters = [
        chapter
        for chapter in analysis_result["chapters"]
        if not (hide_front_matter and is_front_matter(chapter))
    ]
    if not visible_chapters:
        visible_chapters = analysis_result["chapters"]
    visible_rows_global = flatten_oov_rows(visible_chapters)
    visible_unique_oov_words_global = len({row["word"] for row in visible_rows_global})
    visible_total_oov_occurrences = sum(
        sum(row.get("freq", 0) for row in chapter.get("oov_words", []))
        for chapter in visible_chapters
    )
    visible_total_tokens = sum(chapter["total_words"] for chapter in visible_chapters)
    known_coverage = (
        0.0
        if visible_total_tokens == 0
        else max(0.0, 1.0 - (visible_total_oov_occurrences / visible_total_tokens))
    )
    reading_fit = reading_fit_from_coverage(known_coverage)

    top1, top2, top3, top4, top5 = st.columns(5)
    top1.metric(t("unique_words"), f"{analysis_result['total_unique_words']:,}")
    top2.metric(t("chapters"), f"{len(visible_chapters):,}")
    top3.metric(t("unique_unknown_words"), f"{visible_unique_oov_words_global:,}")
    top4.metric(t("known_vocab_size"), f"{analysis_meta.get('vocab_size', 0):,}")
    fit_color = reading_fit_color(known_coverage)
    fit_label = t("reading_fit")
    top5.metric(fit_label, f"{known_coverage:.1%}")
    st.caption(
        (
            f"Estimated coverage only · frequency-list based · Total tokens: {visible_total_tokens:,} · Unknown occurrences: {visible_total_oov_occurrences:,}"
            if st.session_state.get("ui_lang", "en") == "en"
            else f"仅供估计 · 基于词频表 · 总词数：{visible_total_tokens:,} · 生词出现次数：{visible_total_oov_occurrences:,}"
        )
    )
    st.markdown(
        f"**{t('known_source')}:** `{analysis_result['known_words_source'] or 'default'}`"
        if st.session_state.get("ui_lang", "en") == "en"
        else f"**{t('known_source')}：** `{analysis_result['known_words_source'] or 'default'}`"
    )

    search_term = st.text_input(
        t("filter_words"),
        placeholder=(
            "Type to filter unknown words"
            if st.session_state.get("ui_lang", "en") == "en"
            else "输入以筛选不认识的单词"
        ),
    )
    search_term = search_term.strip().lower()

    chapters = visible_chapters
    chapter_mode = st.radio(
        t("chapter_filter"),
        ["chapter_mode_all", "chapter_mode_single", "chapter_mode_range"],
        index=0,
        horizontal=True,
        key="chapter_mode",
        format_func=choice_label,
    )
    st.session_state["last_chapter_mode"] = chapter_mode
    chapter_indices = list(range(len(chapters)))
    st.markdown(f"**{t('chapter_filter')}**")
    if "chapter_filter_initialized" not in st.session_state:
        st.session_state["chapter_start_index"] = 0
        st.session_state["chapter_end_index"] = len(chapter_indices) - 1
        st.session_state["single_chapter_index"] = 0
        st.session_state["chapter_filter_initialized"] = True

    if chapter_mode == "chapter_mode_all":
        selected_chapters = chapters
    elif chapter_mode == "chapter_mode_single":
        single_chapter_indices = [
            idx
            for idx, chapter in enumerate(chapters)
            if chapter_has_visible_oov(
                chapter, hide_undefined_words, show_chinese_definitions
            )
        ]
        if not single_chapter_indices:
            single_chapter_indices = chapter_indices
            st.caption(
                "No chapter currently has visible unknown words, so showing all chapters."
                if st.session_state.get("ui_lang", "en") == "en"
                else "当前没有可见生词的章节，因此显示全部章节。"
            )
        if st.session_state.get("single_chapter_index") not in single_chapter_indices:
            st.session_state["single_chapter_index"] = single_chapter_indices[0]
        with st.container():
            single_index = st.selectbox(
                t("chapter"),
                single_chapter_indices,
                key="single_chapter_index",
                format_func=lambda idx: chapter_label(
                    chapters[idx], hide_undefined_words, show_chinese_definitions
                ),
            )
        selected_chapters = chapters[single_index : single_index + 1]
    else:
        start_col, end_col = st.columns(2)
        with start_col:
            start_index = st.selectbox(
                t("start_chapter"),
                chapter_indices,
                key="chapter_start_index",
                format_func=lambda idx: chapter_label(
                    chapters[idx], hide_undefined_words, show_chinese_definitions
                ),
            )
        end_options = chapter_indices[start_index:]
        if st.session_state.get("chapter_end_index") not in end_options:
            st.session_state["chapter_end_index"] = end_options[-1]
        with end_col:
            end_index = st.selectbox(
                t("end_chapter"),
                end_options,
                key="chapter_end_index",
                format_func=lambda idx: chapter_label(
                    chapters[idx], hide_undefined_words, show_chinese_definitions
                ),
            )
        selected_chapters = chapter_window(chapters, start_index, end_index)
        st.caption(t("range_help"))

    rows = flatten_oov_rows(selected_chapters)
    if search_term:
        rows = [row for row in rows if search_term in row["word"].lower()]

    if show_chinese_definitions and rows:
        unique_words = {row["word"] for row in rows if row.get("word", "").strip()}
        with st.spinner(
            "Loading Chinese definitions..."
            if st.session_state.get("ui_lang", "en") == "en"
            else "正在加载中文释义..."
        ):
            zh_map = {word: translate_word_to_zh(word) for word in unique_words}
        for row in rows:
            row["definition_zh"] = zh_map.get(row["word"], "")
    else:
        for row in rows:
            row.pop("definition_zh", None)

    if hide_undefined_words:
        if show_chinese_definitions:
            rows = [
                row
                for row in rows
                if (row.get("definition_zh") or row.get("definition", "")).strip()
            ]
        else:
            rows = [row for row in rows if row.get("definition", "").strip()]
    visible_unique_oov_words = len({row["word"] for row in rows})
    table_rows = [
        {key: value for key, value in row.items() if key != "context"}
        for row in rows
    ]
    export_signature = hashlib.sha256(
        json.dumps(
            {
                "config": current_input_config,
                "annotation_export_version": ANNOTATION_EXPORT_VERSION,
                "show_chinese_definitions": show_chinese_definitions,
                "show_inline_annotation": show_inline_annotation,
                "show_endnote_annotation": show_endnote_annotation,
            },
            ensure_ascii=True,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if st.session_state.get("annotated_epub_signature") != export_signature:
        st.session_state.pop("annotated_epub_bytes", None)
        st.session_state.pop("show_annotated_epub_direct_link", None)
        st.session_state["annotated_epub_signature"] = export_signature

    table = pd.DataFrame(table_rows)
    if not table.empty:
        table = table.drop(columns=["_chapter_order"], errors="ignore")
        if show_chinese_definitions:
            ordered = [
                col
                for col in [
                    "word",
                    "definition_zh",
                    "definition",
                    "chapter",
                    "freq",
                ]
                if col in table.columns
            ]
        else:
            ordered = [
                col
                for col in ["word", "definition", "chapter", "freq"]
                if col in table.columns
            ]
        table = table[ordered + [col for col in table.columns if col not in ordered]]
    if not show_frequencies and "freq" in table.columns:
        table = table.drop(columns=["freq"])
    table_event = st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="oov_table",
        column_config={
            "word": st.column_config.TextColumn(t("word"), width="medium"),
            "definition_zh": st.column_config.TextColumn(
                t("chinese_definition"), width="large"
            ),
            "definition": st.column_config.TextColumn(t("definition"), width="large"),
            "chapter": st.column_config.TextColumn(t("chapter"), width="medium"),
            "freq": st.column_config.NumberColumn(t("frequency"), format="%d"),
        },
    )
    if rows:
        st.caption(f"{t('book_order_note')} {t('row_hint')}")
        selected_index = selection_row_index(table_event)
        if selected_index is None or selected_index >= len(rows):
            selected_index = 0
        selected_row = rows[selected_index] if rows else None
        if selected_row:
            st.caption(
                "Below is the estimated unknown-word context from the book."
                if st.session_state.get("ui_lang", "en") == "en"
                else "下方显示的是书中对应的预估生词上下文。"
            )
            with st.expander(t("context"), expanded=True):
                st.write(f"**{t('word')}:** {selected_row['word']}")
                st.write(f"**{t('chapter')}:** {selected_row['chapter']}")
                if selected_row.get("definition_zh") and show_chinese_definitions:
                    st.write(
                        f"**{t('chinese_definition')}:** {selected_row['definition_zh']}"
                    )
                st.write(
                    f"**{t('definition')}:** {selected_row.get('definition', '') or '-'}"
                )
                st.write(
                    f"**{t('context')}:** {selected_row.get('context', '') or '-'}"
                )

    st.download_button(
        t("download_anki"),
        data=export_text_payload(
            build_anki_tsv(
                analysis_result,
                use_chinese_definition=show_chinese_definitions,
                hide_undefined_words=hide_undefined_words,
            )
        ),
        file_name="BookVocab_anki_export.tsv",
        mime="text/tab-separated-values",
        key="download_anki",
    )

    annotated_epub_bytes = st.session_state.get("annotated_epub_bytes")
    epub_action_slot = st.empty()
    st.caption(
        "Adjust annotation settings in the sidebar before generating."
        if st.session_state.get("ui_lang", "en") == "en"
        else "生成前可在侧边栏调整注释设置。"
    )
    if annotated_epub_bytes:
        download_name = annotated_epub_download_name(active_epub_name)
        primary_clicked = epub_action_slot.download_button(
            t("download_annotated_epub"),
            data=annotated_epub_bytes,
            file_name=download_name,
            mime="application/epub+zip",
            key="download_annotated_epub_ready",
            type="primary",
        )
        if primary_clicked:
            st.session_state["show_annotated_epub_direct_link"] = True
        st.caption(
            "The file is ready to download, please click the button above"
            if st.session_state.get("ui_lang", "en") == "en"
            else "文件已准备好下载，请点击上面的按钮"
        )
        if st.session_state.get("show_annotated_epub_direct_link", False):
            st.caption(t("download_annotated_epub_direct_hint"))
            render_direct_download_link(
                label=t("download_annotated_epub_direct_link"),
                data=annotated_epub_bytes,
                file_name=download_name,
                mime="application/epub+zip",
            )
    elif epub_action_slot.button(
        t("prepare_annotated_epub"), key="annotated_epub_action", type="primary"
    ):
        if not active_epub_bytes or not active_epub_name:
            st.warning(
                "Please upload an EPUB first."
                if st.session_state.get("ui_lang", "en") == "en"
                else "请先上传 EPUB。"
            )
        else:
            try:
                show_status_toast(
                    "Generating annotated EPUB...",
                    "正在生成带释义 EPUB...",
                )
                progress = st.progress(0)
                with st.spinner(
                    "Preparing annotated EPUB, please do not click elsewhere."
                    if st.session_state.get("ui_lang", "en") == "en"
                    else "正在生成带释义的EPUB，请勿点击其他地方。生成完请后点击下载。"
                ):
                    annotated_epub_bytes = build_annotated_epub_bytes(
                        analysis_result,
                        source_epub_bytes=active_epub_bytes,
                        source_epub_name=active_epub_name,
                        show_inline_annotation=show_inline_annotation,
                        show_endnote_annotation=show_endnote_annotation,
                        show_chinese_definitions=show_chinese_definitions,
                        progress_bar=progress,
                    )
                    st.session_state["annotated_epub_bytes"] = annotated_epub_bytes
                    st.session_state["show_annotated_epub_direct_link"] = False
                progress.empty()
                show_status_toast(
                    "Annotated EPUB is ready.",
                    "带释义 EPUB 已准备好。",
                )
                download_name = annotated_epub_download_name(active_epub_name)
                primary_clicked = epub_action_slot.download_button(
                    t("download_annotated_epub"),
                    data=annotated_epub_bytes,
                    file_name=download_name,
                    mime="application/epub+zip",
                    key="download_annotated_epub_ready_now",
                    type="primary",
                )
                if primary_clicked:
                    st.session_state["show_annotated_epub_direct_link"] = True
                st.caption(
                    "The file is ready to download, please click the button above"
                    if st.session_state.get("ui_lang", "en") == "en"
                    else "文件已准备好下载，请点击上面的按钮"
                )
                if st.session_state.get("show_annotated_epub_direct_link", False):
                    st.caption(t("download_annotated_epub_direct_hint"))
                    render_direct_download_link(
                        label=t("download_annotated_epub_direct_link"),
                        data=annotated_epub_bytes,
                        file_name=download_name,
                        mime="application/epub+zip",
                    )
            except Exception as exc:
                st.error(friendly_failure_message("Annotated EPUB export", exc))
