from __future__ import annotations

import csv
import hashlib
import io
import re
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    from cedict.cedict import DictionaryData, search as cedict_search
except Exception:  # pragma: no cover - optional dependency
    DictionaryData = None
    cedict_search = None

from epub_analyzer import (
    CEFR_TO_WORD_SIZE,
    analyze_epub_file,
    apply_known_words_to_analysis,
    load_known_words,
    normalize_cefr_level,
    parse_known_words_text,
    MAX_KNOWN_WORD_SIZE,
)


st.set_page_config(
    page_title="BookVocab Analyzer",
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
        "sidebar_caption": "Set your English level, vocabulary size, and cleanup filters here.",
        "sidebar_tip": "Use the sidebar to set English level, vocabulary size, and cleanup filters.",
        "epub_file": "EPUB file",
        "vocab_basis": "Vocabulary basis",
        "vocab_mode_level": "English level",
        "vocab_mode_size": "Known vocabulary size",
        "english_level": "English level",
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
        "selectable_words": "Selectable words",
        "download_anki": "Download Anki TSV",
        "download_csv": "Download unknown-word CSV",
        "unique_words": "Unique words",
        "chapters": "Chapters",
        "unique_unknown_words": "Unique unknown words",
        "known_source": "Known words source",
        "visible_filters": "Visible after current filters",
        "dict_defs": "Definitions found for",
        "word": "Word",
        "definition": "Definition",
        "frequency": "Freq",
    },
    "zh": {
        "title": "看书学单词",
        "subtitle": "上传 EPUB，提取章节文本，查看不认识的单词和释义。",
        "language": "语言",
        "sidebar_title": "设置",
        "sidebar_caption": "在这里设置英语水平、词汇量和清理过滤器。",
        "sidebar_tip": "请在侧边栏设置英语水平、词汇量和清理过滤器。",
        "epub_file": "EPUB 文件",
        "vocab_basis": "词汇基准",
        "vocab_mode_level": "英语水平",
        "vocab_mode_size": "已知词汇量",
        "english_level": "英语水平",
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
        "selectable_words": "可复制单词",
        "download_anki": "下载 Anki TSV",
        "download_csv": "下载生词 CSV",
        "unique_words": "唯一词数",
        "chapters": "章节数",
        "unique_unknown_words": "生词数",
        "known_source": "已知词来源",
        "visible_filters": "当前过滤后可见",
        "dict_defs": "有释义的生词数为",
        "word": "单词",
        "definition": "释义",
        "frequency": "频率",
    },
}

LANG_LABELS = {
    "en": "English",
    "zh": "中文",
}


def t(key: str) -> str:
    lang = st.session_state.get("ui_lang", "en")
    return TEXT.get(lang, TEXT["en"]).get(key, TEXT["en"].get(key, key))


def choice_label(key: str) -> str:
    return t(key)


def detect_browser_language() -> str:
    try:
        accept_language = st.context.headers.get("accept-language", "")
    except Exception:
        accept_language = ""
    return "zh" if "zh" in accept_language.lower() else "en"


current_lang = st.session_state.get("ui_lang", "en")


def closest_cefr_level(size: int) -> str:
    levels = list(CEFR_TO_WORD_SIZE.items())
    return min(levels, key=lambda item: abs(item[1] - size))[0]


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


def fingerprint_upload(uploaded_file) -> str:
    return hashlib.sha256(uploaded_file.getvalue()).hexdigest()


def analysis_input_config(
    uploaded_file, remove_stopwords, remove_proper_nouns, min_token_length
) -> dict:
    return {
        "upload_hash": fingerprint_upload(uploaded_file) if uploaded_file else None,
        "remove_stopwords": remove_stopwords,
        "remove_proper_nouns": remove_proper_nouns,
        "min_token_length": min_token_length,
    }


def build_oov_csv(result: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["chapter", "word", "freq", "definition"])
    for chapter in result["chapters"]:
        for row in chapter["oov_words"]:
            writer.writerow(
                [
                    chapter_short_name(chapter),
                    row["word"],
                    row.get("freq", ""),
                    row.get("definition", ""),
                ]
            )
    return buffer.getvalue()


def build_anki_tsv(result: dict, *, use_chinese_definition: bool, hide_undefined_words: bool) -> str:
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


st.header(t("title"))
st.caption(t("subtitle"))
st.info(t("sidebar_tip"))

uploaded_epub = st.file_uploader(t("epub_file"), type=["epub", "zip"])
cefr_level = None

if "cefr_level_pref" not in st.session_state:
    st.session_state["cefr_level_pref"] = "C1"
if "estimated_vocab_pref" not in st.session_state:
    st.session_state["estimated_vocab_pref"] = CEFR_TO_WORD_SIZE["C1"]

with st.sidebar:
    st.header(t("sidebar_title"))
    st.caption(t("sidebar_caption"))
    cefr_level_options = list(CEFR_TO_WORD_SIZE.keys())
    cefr_level = st.selectbox(
        t("english_level"),
        cefr_level_options,
        index=cefr_level_options.index(st.session_state["cefr_level_pref"]),
    )
    st.session_state["cefr_level_pref"] = cefr_level
    expected_vocab_size = CEFR_TO_WORD_SIZE.get(cefr_level, CEFR_TO_WORD_SIZE["C1"])
    vocab_size = st.slider(
        t("estimated_vocab_size"),
        1000,
        MAX_KNOWN_WORD_SIZE,
        value=st.session_state["estimated_vocab_pref"],
        step=1000,
    )
    if vocab_size != st.session_state["estimated_vocab_pref"]:
        st.session_state["estimated_vocab_pref"] = vocab_size
        cefr_level = closest_cefr_level(vocab_size)
        st.session_state["cefr_level_pref"] = cefr_level
        st.rerun()
    elif expected_vocab_size != st.session_state["estimated_vocab_pref"]:
        st.session_state["estimated_vocab_pref"] = expected_vocab_size
        st.session_state["cefr_level_pref"] = cefr_level
        st.rerun()
    st.caption(
        f"{t('english_level')}: {cefr_level} · {t('estimated_vocab_size')}: {vocab_size:,}"
    )
    st.markdown(f"**{t('cleanup_filters')}**")
    remove_stopwords = st.checkbox(t("remove_stopwords"), value=True)
    remove_proper_nouns = st.checkbox(t("remove_proper_nouns"), value=True)
    hide_undefined_words = st.checkbox(t("hide_no_defs"), value=True)
    hide_front_matter = st.checkbox(t("hide_front_matter"), value=False)
    min_token_length = st.slider(t("min_token_length"), 2, 4, 3)
    custom_vocab = st.file_uploader(
        t("optional_vocab"), type=["txt", "csv"], key="vocab"
    )
    show_frequencies = st.checkbox(t("show_freq"), value=False)
    show_chinese_definitions = st.checkbox(
        t("show_zh_definition"),
        value=current_lang == "zh",
        key="show_zh_definition",
    )
    st.divider()
    language = st.radio(
        "Language / 语言",
        ["en", "zh"],
        index=0 if current_lang == "en" else 1,
        format_func=lambda value: LANG_LABELS.get(value, value),
        key="ui_lang",
        horizontal=True,
    )
analysis_result: dict | None = None
analysis_meta: dict | None = None

current_input_config = analysis_input_config(
    uploaded_epub,
    remove_stopwords,
    remove_proper_nouns,
    min_token_length,
)

stored = st.session_state.get("analysis_result")
stored_input_config = st.session_state.get("analysis_input_config")

if uploaded_epub:
    if st.button(t("analyze"), type="primary"):
        epub_path = write_upload_to_tempfile(uploaded_epub)

        custom_words = None
        known_words_source = ""
        if custom_vocab is not None:
            vocab_text = custom_vocab.getvalue().decode("utf-8", errors="ignore")
            custom_words = parse_known_words_text(vocab_text)
            known_words, known_words_source = load_known_words(
                custom_words=custom_words
            )
        else:
            known_words, known_words_source = load_known_words(size=vocab_size)

        try:
            with st.spinner(
                "Analyzing chapters..."
                if st.session_state.get("ui_lang", "en") == "en"
                else "正在分析章节..."
            ):
                analysis_result_obj = analyze_epub_file(
                    epub_path,
                    known_words=known_words,
                    remove_stopwords=remove_stopwords,
                    remove_proper_nouns=remove_proper_nouns,
                    min_token_length=min_token_length,
                    known_words_source=known_words_source,
                )
        except Exception as exc:
            st.error(
                f"Analysis failed: {exc}"
                if st.session_state.get("ui_lang", "en") == "en"
                else f"分析失败：{exc}"
            )
        else:
            analysis_meta = {
                "cefr_level": cefr_level,
                "vocab_size": vocab_size,
                "known_words_source": known_words_source,
            }
            analysis_result = analysis_result_obj.to_dict()
            st.session_state["analysis_input_config"] = current_input_config
            st.session_state["analysis_result"] = analysis_result
            st.session_state["analysis_meta"] = analysis_meta

if stored and stored_input_config == current_input_config:
    analysis_meta = st.session_state.get("analysis_meta")
    analysis_result = stored
elif uploaded_epub and stored and stored_input_config != current_input_config:
    st.info(
        "Current file or text settings differ from the last analysis. Click Analyze EPUB to refresh the raw parse."
        if st.session_state.get("ui_lang", "en") == "en"
        else "当前文件或文本设置与上次分析不同。请点击“分析 EPUB”重新解析。"
    )

if analysis_result:
    if not analysis_result["chapters"]:
        st.warning(
            "No chapter documents were found in this EPUB."
            if st.session_state.get("ui_lang", "en") == "en"
            else "这个 EPUB 没有找到章节内容。"
        )
        st.stop()

    if custom_vocab is not None:
        vocab_text = custom_vocab.getvalue().decode("utf-8", errors="ignore")
        custom_words = parse_known_words_text(vocab_text)
        known_words, known_words_source = load_known_words(custom_words=custom_words)
    else:
        known_words, known_words_source = load_known_words(
            size=vocab_size,
            cefr_level=cefr_level,
        )

    analysis_result = apply_known_words_to_analysis(analysis_result, known_words)
    analysis_result["known_words_source"] = known_words_source
    analysis_meta = {
        "cefr_level": cefr_level,
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
    visible_rows = flatten_oov_rows(visible_chapters)
    visible_total_oov_occurrences = sum(
        sum(row.get("freq", 0) for row in chapter.get("oov_words", []))
        for chapter in visible_chapters
    )
    visible_total_tokens = sum(chapter["total_words"] for chapter in visible_chapters)
    visible_unique_oov_words_global = len({row["word"] for row in visible_rows})
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
            f"Estimated coverage only · frequency-list based"
            if st.session_state.get("ui_lang", "en") == "en"
            else f"仅供估计 · 基于词频表"
        )
    )
    st.caption(
        (
            f"Total token count: {visible_total_tokens:,} · Unknown-word occurrences: {visible_total_oov_occurrences:,}"
            if st.session_state.get("ui_lang", "en") == "en"
            else f"总词数：{visible_total_tokens:,} · 生词出现次数：{visible_total_oov_occurrences:,}"
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
    chapter_indices = list(range(len(chapters)))
    st.markdown(f"**{t('chapter_filter')}**")
    if "chapter_filter_initialized" not in st.session_state:
        st.session_state["chapter_start_index"] = 0
        st.session_state["chapter_end_index"] = len(chapter_indices) - 1
        st.session_state["single_chapter_index"] = 0
        st.session_state["chapter_filter_initialized"] = True

    if chapter_mode == "chapter_mode_all":
        selected_chapters = chapters
        st.caption(t("showing_full"))
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
        rows = [
            row
            for row in rows
            if search_term in row["word"].lower()
            or search_term in row.get("definition", "").lower()
            or search_term in row["chapter"].lower()
        ]
    rows = sorted(rows, key=lambda row: (row["_chapter_order"], row["word"]))
    if show_chinese_definitions and rows:
        unique_words = {row["word"] for row in rows if row.get("word", "").strip()}
        zh_map = {word: translate_word_to_zh(word) for word in unique_words}
        translated_count = sum(1 for value in zh_map.values() if value.strip())
        if translated_count == 0:
            st.warning(
                "Chinese dictionary lookup is not available in this run, so definitions are still shown in English."
                if st.session_state.get("ui_lang", "en") == "en"
                else "当前运行无法提供中文词典查询，所以释义仍显示英文。"
            )
        else:
            st.caption(
                f"Chinese definitions found for {translated_count:,} unique words."
                if st.session_state.get("ui_lang", "en") == "en"
                else f"已转换 {translated_count:,} 个唯一单词的中文释义。"
            )
        for row in rows:
            row["definition_zh"] = zh_map.get(row["word"], "")
    else:
        for row in rows:
            row.pop("definition_zh", None)
    visible_unique_oov_words = len({row["word"] for row in rows})
    defined_unique_oov_words = len(
        {
            row["word"]
            for row in flatten_oov_rows(selected_chapters)
            if row.get("definition", "").strip()
        }
    )

    table = pd.DataFrame(rows)
    if not table.empty:
        table = table.drop(columns=["_chapter_order"], errors="ignore")
        if show_chinese_definitions:
            ordered = [
                col
                for col in ["word", "definition_zh", "definition", "chapter", "freq"]
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
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
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
        st.text_area(
            t("selectable_words"),
            "\n".join(row["word"] for row in rows),
            height=140,
            label_visibility="visible",
        )
    st.caption(
        f"{t('visible_filters')}: {visible_unique_oov_words:,} unique unknown words."
        if st.session_state.get("ui_lang", "en") == "en"
        else f"{t('visible_filters')}：{visible_unique_oov_words:,} 个生词。"
    )
    st.caption(
        f"{t('dict_defs')} {defined_unique_oov_words:,} unique unknown words."
        if st.session_state.get("ui_lang", "en") == "en"
        else f"{t('dict_defs')}{defined_unique_oov_words:,} 个生词。"
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
        file_name="epub_anki_export.tsv",
        mime="text/tab-separated-values",
        key="download_anki",
    )
    st.download_button(
        t("download_csv"),
        data=export_text_payload(build_oov_csv(analysis_result)),
        file_name="epub_unknown_words.csv",
        mime="text/csv",
        key="download_csv",
    )
