from __future__ import annotations

import json
import re
import tempfile
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from urllib.parse import urldefrag
from pathlib import Path
from typing import Iterable, Sequence

from bs4 import BeautifulSoup

try:
    import ebooklib
    from ebooklib import epub
except Exception as exc:  # pragma: no cover - import-time dependency error
    ebooklib = None
    epub = None
    _EBOOKLIB_IMPORT_ERROR = exc
else:
    _EBOOKLIB_IMPORT_ERROR = None

try:
    import spacy
except Exception as exc:  # pragma: no cover - import-time dependency error
    spacy = None
    _SPACY_IMPORT_ERROR = exc
else:
    _SPACY_IMPORT_ERROR = None

try:
    from nltk.corpus import wordnet as wn
except Exception as exc:  # pragma: no cover - import-time dependency error
    wn = None
    _WORDNET_IMPORT_ERROR = exc
else:
    _WORDNET_IMPORT_ERROR = None

from spacy.lang.en.stop_words import STOP_WORDS


WORD_RE = re.compile(r"[a-z]+(?:'[a-z]+)?", re.IGNORECASE)
IELTS_TO_WORD_SIZE = {
    "4.0": 1000,
    "4.5": 2000,
    "5.0": 4000,
    "5.5": 6000,
    "6.0": 12000,
    "6.5": 16000,
    "7.0": 20000,
    "7.5": 25000,
    "8.0": 30000,
}
CEFR_TO_WORD_SIZE = IELTS_TO_WORD_SIZE
DEFAULT_KNOWN_WORD_SIZE = 12000
MAX_KNOWN_WORD_SIZE = 30000


@dataclass
class ChapterResult:
    chapter_id: str
    title: str
    total_words: int
    unique_words: int
    text: str = ""
    frequencies: dict[str, int] = field(default_factory=dict)
    definitions: dict[str, str] = field(default_factory=dict)
    oov_words: list[dict[str, object]] = field(default_factory=list)


@dataclass
class AnalysisResult:
    chapters: list[ChapterResult]
    global_frequencies: dict[str, int]
    global_oov_words: list[dict[str, object]]
    total_words: int
    total_unique_words: int
    total_oov_words: int
    known_words_source: str

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=True, indent=2)


def load_spacy_model():
    if spacy is None:
        raise RuntimeError(
            "spaCy is not installed. Install dependencies before running the app."
        ) from _SPACY_IMPORT_ERROR

    try:
        nlp = spacy.load("en_core_web_sm", disable=["ner"])
    except Exception:
        nlp = spacy.blank("en")
        if "lemmatizer" not in nlp.pipe_names:
            nlp.add_pipe("lemmatizer", config={"mode": "rule"})
        if "sentencizer" not in nlp.pipe_names:
            nlp.add_pipe("sentencizer")
        try:
            nlp.initialize()
        except Exception:
            pass
    else:
        if "sentencizer" not in nlp.pipe_names:
            nlp.add_pipe("sentencizer")

    nlp.max_length = max(nlp.max_length, 5_000_000)
    return nlp


def fallback_lemma(text: str) -> str:
    token = normalize_token(text)
    if len(token) <= 3:
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("ing") and len(token) > 5:
        return token[:-3]
    if token.endswith("ed") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


def normalize_word_form(word: str) -> str:
    token = normalize_token(word)
    return fallback_lemma(token)


def resolve_known_word_size(
    *,
    vocabulary_size: int | None = None,
    cefr_level: str | None = None,
) -> int:
    if vocabulary_size:
        return min(vocabulary_size, MAX_KNOWN_WORD_SIZE)
    if cefr_level and cefr_level in CEFR_TO_WORD_SIZE:
        return CEFR_TO_WORD_SIZE[cefr_level]
    return DEFAULT_KNOWN_WORD_SIZE


def normalize_cefr_level(level: str | None) -> str | None:
    if not level:
        return None
    value = level.strip().upper()
    return value if value in CEFR_TO_WORD_SIZE else None


def clean_html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def extract_html_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    candidates = []
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        candidates.append(title_tag.get_text(" ", strip=True))

    for heading in soup.find_all(["h1", "h2", "h3"]):
        text = heading.get_text(" ", strip=True)
        if text:
            candidates.append(text)
            break

    for candidate in candidates:
        cleaned = re.sub(r"\s+", " ", candidate).strip()
        if cleaned:
            return cleaned
    return ""


def normalize_href(href: str | None) -> str:
    if not href:
        return ""
    href, _fragment = urldefrag(href)
    return href.replace("\\", "/").strip()


def flatten_toc(entries) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for entry in entries or []:
        if isinstance(entry, tuple) and len(entry) == 2:
            node, children = entry
            title = getattr(node, "title", "") or ""
            href = normalize_href(getattr(node, "href", "") or "")
            if href and title:
                items.append((href, title))
            items.extend(flatten_toc(children))
        else:
            href = normalize_href(getattr(entry, "href", "") or "")
            title = getattr(entry, "title", "") or ""
            if href and title:
                items.append((href, title))
    return items


def is_zip_path(path: str | Path) -> bool:
    return zipfile.is_zipfile(path)


def has_epub_container(entries: Sequence[str]) -> bool:
    normalized = [entry.replace("\\", "/").lstrip("./") for entry in entries]
    if "META-INF/container.xml" in normalized:
        return True
    return any(entry.endswith("/META-INF/container.xml") for entry in normalized)


def strip_single_root_prefix(entries: Sequence[str]) -> str | None:
    normalized = [entry.replace("\\", "/").lstrip("./") for entry in entries if entry and not entry.endswith("/")]
    if not normalized:
        return None

    top_levels = {entry.split("/", 1)[0] for entry in normalized if "/" in entry}
    if len(top_levels) != 1:
        return None

    prefix = next(iter(top_levels))
    if prefix in {"META-INF", "mimetype"}:
        return None
    return prefix + "/"


def rebuild_zip_without_prefix(source: str | Path, prefix: str) -> Path:
    source_path = Path(source)
    with zipfile.ZipFile(source_path, "r") as src, tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as dst:
            for info in src.infolist():
                name = info.filename.replace("\\", "/")
                if name.endswith("/"):
                    continue
                if name.startswith(prefix):
                    name = name[len(prefix) :]
                if not name:
                    continue
                data = src.read(info.filename)
                dst.writestr(name, data)
        return Path(tmp.name)


def resolve_epub_source(epub_path: str | Path) -> Path:
    path = Path(epub_path)
    if not is_zip_path(path):
        return path

    with zipfile.ZipFile(path, "r") as archive:
        names = archive.namelist()
        epub_members = [name for name in names if name.lower().endswith(".epub") and not name.endswith("/")]
        if len(epub_members) == 1:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp:
                tmp.write(archive.read(epub_members[0]))
                return Path(tmp.name)

        if has_epub_container(names):
            root_prefix = strip_single_root_prefix(names)
            if root_prefix:
                return rebuild_zip_without_prefix(path, root_prefix)
            return path

    raise ValueError(
        "The uploaded ZIP does not contain a valid EPUB structure. "
        "It needs META-INF/container.xml at the archive root or a single .epub file inside."
    )


def load_known_words(
    size: int = DEFAULT_KNOWN_WORD_SIZE,
    cefr_level: str | None = None,
    custom_words: Iterable[str] | None = None,
) -> tuple[set[str], str]:
    if custom_words is not None:
        words = {normalize_word_form(word) for word in custom_words}
        words.discard("")
        return words, "custom upload"

    size = resolve_known_word_size(vocabulary_size=size, cefr_level=normalize_cefr_level(cefr_level))
    try:
        from wordfreq import top_n_list

        collected: list[str] = []
        seen: set[str] = set()
        request_size = max(size * 4, 20000)

        while len(collected) < size and request_size <= 200000:
            for word in top_n_list("en", request_size):
                normalized = normalize_word_form(word)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                collected.append(normalized)
                if len(collected) >= size:
                    break
            if len(collected) < size:
                request_size *= 2

        if len(collected) < size:
            return set(collected), f"wordfreq top {len(collected)} unique normalized words"

        return set(collected[:size]), f"wordfreq top {size} unique normalized words"
    except Exception:
        words = {normalize_word_form(word) for word in STOP_WORDS}
        return words, "spaCy stop-word fallback"


def parse_known_words_text(text: str) -> list[str]:
    tokens: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        tokens.extend(WORD_RE.findall(line))
    return tokens


def normalize_token(token: str) -> str:
    token = token.lower().strip()
    token = re.sub(r"[^a-z']", "", token)
    token = token.strip("'")
    return token


def wordnet_pos(token_pos: str | None) -> str | None:
    if wn is None or not token_pos:
        return None
    mapping = {
        "NOUN": wn.NOUN,
        "VERB": wn.VERB,
        "ADJ": wn.ADJ,
        "ADV": wn.ADV,
    }
    return mapping.get(token_pos)


@lru_cache(maxsize=50000)
def lookup_definitions(word: str, pos: str | None = None) -> tuple[str, ...]:
    if wn is None:
        return ()

    try:
        synsets = wn.synsets(word, pos=pos) if pos else wn.synsets(word)
    except LookupError:
        return ()

    definitions: list[str] = []
    for synset in synsets[:3]:
        definition = synset.definition().strip()
        if definition and definition not in definitions:
            definitions.append(definition)
    return tuple(definitions[:2])


def is_dictionary_word(word: str, pos: str | None = None) -> bool:
    return bool(lookup_definitions(word, pos))


def extract_epub_documents(epub_path: str | Path) -> list[tuple[str, str]]:
    if epub is None:
        raise RuntimeError(
            "ebooklib is not installed. Install dependencies before running the app."
        ) from _EBOOKLIB_IMPORT_ERROR

    resolved_path = resolve_epub_source(epub_path)
    book = epub.read_epub(str(resolved_path))
    chapters: list[tuple[str, str]] = []
    toc_titles = {}
    for href, title in flatten_toc(getattr(book, "toc", [])):
        toc_titles.setdefault(normalize_href(href), title)

    spine_ids = [item_id for item_id, linear in getattr(book, "spine", []) if item_id != "nav"]
    spine_items = []
    for item_id in spine_ids:
        try:
            item = book.get_item_with_id(item_id)
        except Exception:
            item = None
        if item is not None and item.get_type() == ebooklib.ITEM_DOCUMENT:
            spine_items.append(item)

    if not spine_items:
        spine_items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))

    for index, item in enumerate(spine_items, start=1):
        raw_html = item.get_content().decode("utf-8", errors="ignore")
        text = clean_html_to_text(raw_html)
        item_name = normalize_href(getattr(item, "get_name", lambda: None)() or getattr(item, "file_name", ""))
        chapter_name = (
            toc_titles.get(item_name)
            or extract_html_title(raw_html)
            or Path(item_name).stem
            or f"chapter_{index}"
        )
        chapters.append((chapter_name, text))

    return chapters


def analyze_chapters(
    chapters: Sequence[tuple[str, str]],
    *,
    remove_stopwords: bool = False,
    remove_proper_nouns: bool = False,
    min_token_length: int = 2,
) -> AnalysisResult:
    nlp = load_spacy_model()
    chapter_results: list[ChapterResult] = []
    global_counter: Counter[str] = Counter()
    total_words = 0

    for index, (chapter_title, text) in enumerate(chapters, start=1):
        doc = nlp(text)
        counter: Counter[str] = Counter()
        definitions: dict[str, str] = {}
        occurrences: dict[str, dict[str, object]] = {}

        for token_index, token in enumerate(doc):
            if token.is_space or token.is_punct or token.like_num:
                continue
            if remove_stopwords and token.is_stop:
                continue
            if remove_proper_nouns and token.pos_ == "PROPN":
                continue

            lemma = token.lemma_ if token.lemma_ and token.lemma_ != "-PRON-" else token.text
            normalized = normalize_word_form(lemma) or fallback_lemma(token.text)
            if len(normalized) < min_token_length:
                continue
            if not normalized or not WORD_RE.fullmatch(normalized):
                continue
            if len(normalized) > 24:
                continue

            pos = wordnet_pos(token.pos_)
            definition_list = lookup_definitions(normalized, pos)
            context = ""
            try:
                context = token.sent.text.strip()
            except Exception:
                context = ""

            counter[normalized] += 1
            if definition_list:
                definitions.setdefault(normalized, definition_list[0])
            if normalized not in occurrences:
                occurrences[normalized] = {
                    "word": normalized,
                    "freq": 0,
                    "definition": definition_list[0] if definition_list else "",
                    "context": context,
                    "first_index": token_index,
                }
            occurrences[normalized]["freq"] = int(occurrences[normalized]["freq"]) + 1
            if not occurrences[normalized].get("definition") and definition_list:
                occurrences[normalized]["definition"] = definition_list[0]
            if not occurrences[normalized].get("context") and context:
                occurrences[normalized]["context"] = context

        global_counter.update(counter)
        chapter_total = sum(counter.values())
        total_words += chapter_total
        chapter_id = f"chapter_{index}"
        ordered_occurrences = sorted(
            occurrences.values(),
            key=lambda item: (int(item.get("first_index", 0)), str(item.get("word", ""))),
        )
        chapter_results.append(
            ChapterResult(
                chapter_id=chapter_id,
                title=chapter_title,
                total_words=chapter_total,
                unique_words=len(counter),
                text=text,
                frequencies=dict(counter.most_common()),
                definitions=definitions,
                oov_words=[dict(item) for item in ordered_occurrences],
            )
        )

    return AnalysisResult(
        chapters=chapter_results,
        global_frequencies=dict(global_counter.most_common()),
        global_oov_words=[],
        total_words=total_words,
        total_unique_words=len(global_counter),
        total_oov_words=0,
        known_words_source="",
    )


def lookup_word_definition(word: str) -> str:
    definitions = lookup_definitions(word)
    return definitions[0] if definitions else ""


def apply_known_words_to_analysis(result: AnalysisResult | dict, known_words: set[str]) -> dict:
    if isinstance(result, AnalysisResult):
        raw = result.to_dict()
    else:
        raw = result

    chapters = []
    global_oov_map: dict[str, dict[str, object]] = {}
    total_oov_words = 0

    for chapter in raw["chapters"]:
        oov_words = []
        for word, freq in chapter["frequencies"].items():
            if word not in known_words:
                definition = chapter.get("definitions", {}).get(word, lookup_word_definition(word))
                chapter_oov = next(
                    (item for item in chapter.get("oov_words", []) if item.get("word") == word),
                    None,
                )
                oov_words.append(
                    {
                        "word": word,
                        "freq": freq,
                        "definition": definition,
                        "context": (chapter_oov or {}).get("context", ""),
                        "first_index": (chapter_oov or {}).get("first_index", 0),
                    }
                )
                existing = global_oov_map.get(word)
                if existing is None:
                    global_oov_map[word] = {
                        "word": word,
                        "freq": freq,
                        "definition": definition,
                        "context": (chapter_oov or {}).get("context", ""),
                        "chapter_id": chapter["chapter_id"],
                        "chapter": chapter["title"],
                        "first_index": (chapter_oov or {}).get("first_index", 0),
                    }
                else:
                    existing["freq"] = max(int(existing["freq"]), freq)
                total_oov_words += freq
        chapter_copy = dict(chapter)
        chapter_copy["oov_words"] = sorted(
            oov_words, key=lambda item: (int(item.get("first_index", 0)), str(item["word"]))
        )
        chapters.append(chapter_copy)

    global_oov = sorted(
        global_oov_map.values(),
        key=lambda item: (int(item.get("first_index", 0)), str(item["word"]))
    )
    raw["chapters"] = chapters
    raw["global_oov_words"] = global_oov
    raw["total_oov_words"] = total_oov_words
    return raw


def analyze_epub_file(
    epub_path: str | Path,
    *,
    known_words: set[str],
    remove_stopwords: bool = False,
    remove_proper_nouns: bool = False,
    min_token_length: int = 2,
    known_words_source: str = "",
) -> AnalysisResult:
    chapters = extract_epub_documents(epub_path)
    result = analyze_chapters(
        chapters,
        remove_stopwords=remove_stopwords,
        remove_proper_nouns=remove_proper_nouns,
        min_token_length=min_token_length,
    )
    result.known_words_source = known_words_source
    return result
