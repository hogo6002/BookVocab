from __future__ import annotations

from pathlib import Path

from epub_analyzer import DEFAULT_KNOWN_WORD_SIZE, normalize_word_form


def export_wordfreq_known_words(size: int = DEFAULT_KNOWN_WORD_SIZE) -> list[str]:
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

    return collected[:size]


def main() -> None:
    out_path = Path("known_words_top12000.txt")
    words = export_wordfreq_known_words()
    out_path.write_text("\n".join(words) + "\n", encoding="utf-8")
    print(f"Wrote {len(words)} words to {out_path}")


if __name__ == "__main__":
    main()
