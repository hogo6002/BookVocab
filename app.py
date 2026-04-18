from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from epub_analyzer import (
    CEFR_TO_WORD_SIZE,
    analyze_epub_file,
    apply_known_words_to_analysis,
    load_known_words,
    normalize_cefr_level,
    parse_known_words_text,
MAX_KNOWN_WORD_SIZE,
)


st.set_page_config(page_title="EPUB Vocabulary Analyzer", layout="wide")


def write_upload_to_tempfile(uploaded_file) -> Path:
    suffix = Path(uploaded_file.name).suffix or ".epub"
    if suffix.lower() == ".zip":
        suffix = ".epub"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getvalue())
        return Path(tmp.name)


def fingerprint_upload(uploaded_file) -> str:
    return hashlib.sha256(uploaded_file.getvalue()).hexdigest()


def analysis_input_config(uploaded_file, remove_stopwords, remove_proper_nouns, min_token_length) -> dict:
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
            writer.writerow([chapter_short_name(chapter), row["word"], row.get("freq", ""), row.get("definition", "")])
    return buffer.getvalue()


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
    match = re.search(r"\bch(?:apter)?\.?\s*([0-9]+|[ivxlcdm]+)\b", title, flags=re.IGNORECASE)
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
        count = sum(1 for row in chapter.get("oov_words", []) if row.get("definition", "").strip())
    else:
        count = len(chapter.get("oov_words", []))
    title = chapter_short_name(chapter)
    number = extract_chapter_number(title)
    if title.lower().startswith("chapter "):
        return f"{title} ({count})"
    if number:
        return f"Chapter {number} · {title} ({count})"
    return f"{title} ({count})"


def chapter_window(chapters: list[dict], start_index: int, end_index: int) -> list[dict]:
    try:
        return chapters[start_index : end_index + 1]
    except Exception:
        return chapters


st.title("EPUB Vocabulary Analyzer")
st.caption("Upload an EPUB, extract chapter text, and surface likely unknown words with definitions.")

uploaded_epub = st.file_uploader("EPUB file", type=["epub", "zip"])
cefr_level = None

with st.sidebar:
    st.header("Analysis settings")
    vocab_mode = st.radio("Vocabulary basis", ["English level", "Known vocabulary size"], index=0)
    st.session_state["vocab_mode"] = vocab_mode
    if vocab_mode == "English level":
        cefr_level = st.selectbox("English level", list(CEFR_TO_WORD_SIZE.keys()), index=3, key="cefr_level_choice")
        st.session_state["cefr_level"] = cefr_level
        suggested_size = CEFR_TO_WORD_SIZE[normalize_cefr_level(cefr_level) or "B2"]
        if (
            st.session_state.get("last_vocab_mode") != "English level"
            or st.session_state.get("last_cefr_level") != cefr_level
            or "estimated_vocab_size" not in st.session_state
        ):
            st.session_state["estimated_vocab_size"] = suggested_size
        vocab_size = st.slider(
            "Estimated vocabulary size",
            1000,
            MAX_KNOWN_WORD_SIZE,
            key="estimated_vocab_size",
            step=1000,
        )
        st.caption(f"Suggested size for {cefr_level}: {suggested_size:,} (cap: {MAX_KNOWN_WORD_SIZE:,})")
    else:
        st.session_state["cefr_level"] = None
        if st.session_state.get("last_vocab_mode") != "Known vocabulary size" or "manual_vocab_size" not in st.session_state:
            st.session_state["manual_vocab_size"] = 10000
        vocab_size = st.number_input(
            "Known vocabulary size",
            min_value=1000,
            max_value=MAX_KNOWN_WORD_SIZE,
            key="manual_vocab_size",
            step=5000,
        )
    st.session_state["last_vocab_mode"] = vocab_mode
    st.session_state["last_cefr_level"] = cefr_level
    st.markdown("**Cleanup filters**")
    remove_stopwords = st.checkbox("Remove stopwords", value=True)
    remove_proper_nouns = st.checkbox("Remove proper nouns", value=True)
    hide_undefined_words = st.checkbox("Hide words without definitions", value=True)
    hide_front_matter = st.checkbox("Hide front matter / non-chapters", value=False)
    min_token_length = st.slider("Minimum token length", 2, 4, 3)
    custom_vocab = st.file_uploader("Optional known-words list", type=["txt", "csv"], key="vocab")
    show_frequencies = st.checkbox("Show frequencies", value=False)
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
    if Path(uploaded_epub.name).suffix.lower() == ".zip":
        st.info("This file was uploaded as a ZIP. EPUB files are ZIP containers, so the app will treat it as an EPUB.")

    if st.button("Analyze EPUB", type="primary"):
        epub_path = write_upload_to_tempfile(uploaded_epub)

        custom_words = None
        known_words_source = ""
        if custom_vocab is not None:
            vocab_text = custom_vocab.getvalue().decode("utf-8", errors="ignore")
            custom_words = parse_known_words_text(vocab_text)
            known_words, known_words_source = load_known_words(custom_words=custom_words)
        else:
            known_words, known_words_source = load_known_words(size=vocab_size)

        try:
            with st.spinner("Analyzing chapters..."):
                analysis_result_obj = analyze_epub_file(
                    epub_path,
                    known_words=known_words,
                    remove_stopwords=remove_stopwords,
                    remove_proper_nouns=remove_proper_nouns,
                    min_token_length=min_token_length,
                    known_words_source=known_words_source,
                )
        except Exception as exc:
            st.error(f"Analysis failed: {exc}")
        else:
            analysis_meta = {
                "vocab_mode": vocab_mode,
                "cefr_level": st.session_state.get("cefr_level"),
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
    st.info("Current file or text settings differ from the last analysis. Click Analyze EPUB to refresh the raw parse.")

if analysis_result:
    if not analysis_result["chapters"]:
        st.warning("No chapter documents were found in this EPUB.")
        st.stop()

    if custom_vocab is not None:
        vocab_text = custom_vocab.getvalue().decode("utf-8", errors="ignore")
        custom_words = parse_known_words_text(vocab_text)
        known_words, known_words_source = load_known_words(custom_words=custom_words)
    else:
        known_words, known_words_source = load_known_words(
            size=vocab_size,
            cefr_level=cefr_level if vocab_mode == "English level" else None,
        )

    analysis_result = apply_known_words_to_analysis(analysis_result, known_words)
    analysis_result["known_words_source"] = known_words_source
    analysis_meta = {
        "vocab_mode": vocab_mode,
        "cefr_level": cefr_level,
        "vocab_size": vocab_size,
        "known_words_source": known_words_source,
    }

    visible_chapters = [chapter for chapter in analysis_result["chapters"] if not (hide_front_matter and is_front_matter(chapter))]
    if not visible_chapters:
        visible_chapters = analysis_result["chapters"]
    visible_rows = flatten_oov_rows(visible_chapters)
    visible_total_oov_occurrences = sum(sum(row.get("freq", 0) for row in chapter.get("oov_words", [])) for chapter in visible_chapters)
    visible_unique_oov_words_global = len({row["word"] for row in visible_rows})

    top1, top2, top3, top4 = st.columns(4)
    top1.metric("Unique words", f"{analysis_result['total_unique_words']:,}")
    top2.metric("Chapters", f"{len(visible_chapters):,}")
    top3.metric("Unique OOV words", f"{visible_unique_oov_words_global:,}")
    top4.metric("Known vocabulary size", f"{analysis_meta.get('vocab_size', 0):,}")
    st.caption(
        f"Total token count: {sum(chapter['total_words'] for chapter in visible_chapters):,} · "
        f"Total OOV occurrences: {visible_total_oov_occurrences:,}"
    )
    st.markdown(f"**Known words source:** `{analysis_result['known_words_source'] or 'default'}`")

    search_term = st.text_input("Filter words", placeholder="Type to filter unknown words")
    search_term = search_term.strip().lower()

    chapters = visible_chapters
    chapter_mode = st.radio(
        "Chapter mode",
        ["All chapters", "Single chapter", "Chapter range"],
        index=0,
        horizontal=True,
        key="chapter_mode",
    )
    chapter_indices = list(range(len(chapters)))
    st.markdown("**Chapter filter**")
    if "chapter_filter_initialized" not in st.session_state:
        st.session_state["chapter_start_index"] = 0
        st.session_state["chapter_end_index"] = len(chapter_indices) - 1
        st.session_state["single_chapter_index"] = 0
        st.session_state["chapter_filter_initialized"] = True

    if chapter_mode == "All chapters":
        selected_chapters = chapters
        st.caption("Showing the full book.")
    elif chapter_mode == "Single chapter":
        with st.container():
            single_index = st.selectbox(
                "Chapter",
                chapter_indices,
                key="single_chapter_index",
                format_func=lambda idx: chapter_label(chapters[idx], hide_undefined_words),
            )
        selected_chapters = chapters[single_index : single_index + 1]
    else:
        start_col, end_col = st.columns(2)
        with start_col:
            start_index = st.selectbox(
                "Start chapter",
                chapter_indices,
                key="chapter_start_index",
                format_func=lambda idx: chapter_label(chapters[idx], hide_undefined_words),
            )
        end_options = chapter_indices[start_index:]
        if st.session_state.get("chapter_end_index") not in end_options:
            st.session_state["chapter_end_index"] = end_options[-1]
        with end_col:
            end_index = st.selectbox(
                "End chapter",
                end_options,
                key="chapter_end_index",
                format_func=lambda idx: chapter_label(chapters[idx], hide_undefined_words),
            )
        selected_chapters = chapter_window(chapters, start_index, end_index)
        st.caption("Set start and end to the same chapter for a single-chapter view, or extend end to include later chapters.")

    rows = flatten_oov_rows(selected_chapters)
    if hide_undefined_words:
        rows = [row for row in rows if row.get("definition", "").strip()]
    if search_term:
        rows = [
            row for row in rows
            if search_term in row["word"].lower()
            or search_term in row.get("definition", "").lower()
            or search_term in row["chapter"].lower()
        ]
    rows = sorted(rows, key=lambda row: (row["_chapter_order"], row["word"]))
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
        ordered = [col for col in ["word", "definition", "chapter", "freq"] if col in table.columns]
        table = table[ordered + [col for col in table.columns if col not in ordered]]
    if not show_frequencies and "freq" in table.columns:
        table = table.drop(columns=["freq"])
    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
        column_config={
            "definition": st.column_config.TextColumn("definition", width="large"),
            "chapter": st.column_config.TextColumn("chapter", width="medium"),
        },
    )
    if rows:
        st.text_area(
            "Selectable words",
            "\n".join(row["word"] for row in rows),
            height=140,
            label_visibility="visible",
        )
    st.caption(f"Visible after current filters: {visible_unique_oov_words:,} unique OOV words.")
    st.caption(f"Dictionary definitions found for {defined_unique_oov_words:,} unique OOV words.")

    export_json = json.dumps(analysis_result, indent=2)
    st.download_button(
        "Download JSON",
        data=export_json,
        file_name="epub_vocabulary_analysis.json",
        mime="application/json",
    )
    st.download_button(
        "Download OOV CSV",
        data=build_oov_csv(analysis_result),
        file_name="epub_oov_words.csv",
        mime="text/csv",
    )
