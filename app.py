from __future__ import annotations

import base64
import csv
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
import streamlit.components.v1 as components

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


st.set_page_config(
    page_title="BookVocab Analyzer",
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
        "subtitle": "Upload an EPUB, extract chapter text, and surface likely unknown words with definitions.",
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
    },
    "zh": {
        "title": "看书学单词",
        "subtitle": "上传 EPUB，提取章节文本，查看不认识的单词和释义。",
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
        "context": "语境",
        "book_order_note": "单词按在书中出现的顺序显示。",
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


def write_upload_to_tempfile(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix or ".epub"
    if suffix.lower() == ".zip":
        suffix = ".epub"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        return Path(tmp.name)


def store_uploaded_file(
    uploaded_file, *, bytes_key: str, name_key: str, hash_key: str
) -> bytes:
    data = uploaded_file.getvalue()
    st.session_state[bytes_key] = data
    st.session_state[name_key] = uploaded_file.name
    st.session_state[hash_key] = hashlib.sha256(data).hexdigest()
    return data


def fingerprint_upload(uploaded_file) -> str:
    return hashlib.sha256(uploaded_file.getvalue()).hexdigest()


def analysis_input_config(
    epub_hash: str | None,
    remove_stopwords: bool,
    remove_proper_nouns: bool,
    min_token_length: int,
    vocab_size: int,
    custom_vocab_hash: str | None,
) -> dict:
    return {
        "upload_hash": epub_hash,
        "remove_stopwords": remove_stopwords,
        "remove_proper_nouns": remove_proper_nouns,
        "min_token_length": min_token_length,
        "vocab_size": vocab_size,
        "custom_vocab_hash": custom_vocab_hash,
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


def trigger_browser_download(data: bytes, file_name: str, mime: str) -> None:
    encoded = base64.b64encode(data).decode("ascii")
    safe_name = html.escape(file_name, quote=True)
    components.html(
        f"""
        <a id="bookvocab-download" download="{safe_name}" href="data:{mime};base64,{encoded}"></a>
        <script>
          const link = document.getElementById("bookvocab-download");
          if (link) {{
            setTimeout(() => link.click(), 0);
          }}
        </script>
        """,
        height=0,
    )


def chapter_definition_map(
    chapter: dict, *, use_chinese_definition: bool
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in chapter.get("oov_words", []):
        word = row.get("word", "").strip().lower()
        if not word:
            continue
        definition = ""
        if use_chinese_definition:
            definition = translate_word_to_zh(word) or row.get("definition", "")
        else:
            definition = row.get("definition", "")
        if definition.strip():
            mapping[word] = definition.strip()
    return mapping


def annotate_text_for_epub(text: str, definitions: dict[str, str]) -> str:
    if not text:
        return "<p></p>"

    nlp = load_spacy_model()
    doc = nlp(text)
    parts: list[str] = []
    seen_words: set[str] = set()

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
        gloss = definitions.get(normalized, "")
        if gloss and normalized not in seen_words:
            token_text = html.escape(token.text)
            token_ws = html.escape(token.whitespace_)
            gloss_html = html.escape(gloss)
            parts.append(
                f'<span style="text-decoration:underline;">{token_text}</span>'
                f" [{gloss_html}]{token_ws}"
            )
            seen_words.add(normalized)
        else:
            parts.append(html.escape(token.text_with_ws))

    body = "".join(parts).replace("\n", "<br/>")
    return (
        '<html xmlns="http://www.w3.org/1999/xhtml">'
        "<head>"
        '<meta charset="utf-8"/>'
        "<style>"
        "body{font-family:serif;line-height:1.6;margin:1em;}"
        "p{margin:0 0 1em 0;}"
        "</style>"
        "</head><body><p>"
        f"{body}"
        "</p></body></html>"
    )


def build_annotated_epub_bytes(
    result: dict,
    *,
    source_epub_bytes: bytes,
    source_epub_name: str,
    use_chinese_definition: bool,
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
        book.set_title(f"{book.title or 'Book'} (BookVocab version)")
        chapter_results = result.get("chapters", [])
        document_items = [
            item for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)
        ]
        for chapter_index, (chapter, item) in enumerate(
            zip(chapter_results, document_items), start=1
        ):
            defs = chapter_definition_map(
                chapter, use_chinese_definition=use_chinese_definition
            )
            item.content = annotate_text_for_epub(chapter.get("text", ""), defs)
            if progress_bar is not None:
                total = max(len(chapter_results), 1)
                progress_bar.progress(min(chapter_index / total, 1.0))
        book.add_item(ebooklib_epub.EpubNcx())
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


def chapter_label(chapter: dict, hide_undefined_words: bool) -> str:
    if hide_undefined_words:
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


def chapter_has_visible_oov(chapter: dict, hide_undefined_words: bool) -> bool:
    if hide_undefined_words:
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
    if "show_zh_definition" not in st.session_state:
        st.session_state["show_zh_definition"] = current_lang == "zh"
    show_chinese_definitions = st.checkbox(t("show_zh_definition"), key="show_zh_definition")
    hide_front_matter = st.checkbox(t("hide_front_matter"), value=False)
    show_frequencies = st.checkbox(t("show_freq"), value=False)
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
    custom_vocab_hash = (
        hashlib.sha256(custom_vocab_text.encode("utf-8")).hexdigest()
        if custom_vocab_text
        else None
    )
analysis_result: dict | None = None
analysis_meta: dict | None = None

current_input_config = analysis_input_config(
    uploaded_epub_hash,
    remove_stopwords,
    remove_proper_nouns,
    min_token_length,
    vocab_size,
    custom_vocab_hash,
)

stored = st.session_state.get("analysis_result")
stored_input_config = st.session_state.get("analysis_input_config")

active_epub_bytes = uploaded_epub_bytes
active_epub_name = uploaded_epub_name

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

analysis_ready = bool(analysis_result) or bool(
    stored and stored_input_config == current_input_config
)
if uploaded_epub_bytes and not analysis_ready:
    st.caption(
        "If upload fails once, try again. That is usually a temporary browser or network issue."
        if st.session_state.get("ui_lang", "en") == "en"
        else "如果上传第一次失败，请再试一次。通常是浏览器或网络的临时问题。"
    )

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
            if chapter_has_visible_oov(chapter, hide_undefined_words)
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
                    chapters[idx], hide_undefined_words
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
                    chapters[idx], hide_undefined_words
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
                    chapters[idx], hide_undefined_words
                ),
            )
        selected_chapters = chapter_window(chapters, start_index, end_index)
        st.caption(t("range_help"))

    rows = flatten_oov_rows(selected_chapters)
    if hide_undefined_words:
        rows = [row for row in rows if row.get("definition", "").strip()]
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
    visible_unique_oov_words = len({row["word"] for row in rows})
    export_signature = hashlib.sha256(
        json.dumps(
            {
                "config": current_input_config,
                "show_chinese_definitions": show_chinese_definitions,
            },
            ensure_ascii=True,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if st.session_state.get("annotated_epub_signature") != export_signature:
        st.session_state.pop("annotated_epub_bytes", None)
        st.session_state["annotated_epub_signature"] = export_signature

    table = pd.DataFrame(rows)
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
        st.caption(t("book_order_note"))
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
    if st.button(t("download_annotated_epub"), key="annotated_epub_action", type="primary"):
        if not active_epub_bytes or not active_epub_name:
            st.warning(
                "Please upload an EPUB first."
                if st.session_state.get("ui_lang", "en") == "en"
                else "请先上传 EPUB。"
            )
        else:
            try:
                if not annotated_epub_bytes:
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
                            use_chinese_definition=show_chinese_definitions,
                            progress_bar=progress,
                        )
                        st.session_state["annotated_epub_bytes"] = annotated_epub_bytes
                    progress.empty()
                if annotated_epub_bytes:
                    trigger_browser_download(
                        annotated_epub_bytes,
                        annotated_epub_download_name(active_epub_name),
                        "application/epub+zip",
                    )
            except Exception as exc:
                st.error(friendly_failure_message("Annotated EPUB export", exc))
