# Codex Handoff

Read this first in a new Codex session.

## Project

BookVocab is a Streamlit app for English learners to upload an EPUB, extract chapter text, identify likely unknown words, review definitions/context, and export study files.

## What the app does now

- Upload `.epub` files. `.zip` is accepted as an EPUB container, but the UI now says EPUB.
- Analyze EPUB text with `epub_analyzer.py`.
- Filter unknown words by:
  - known vocabulary size
  - stopwords
  - proper nouns
  - words without definitions
  - front matter / non-chapters
  - minimum token length
- Show results in a book-order table.
- Show context (`上下文` in Chinese UI) for the selected row in a detail card below the table.
- Export:
  - Anki TSV
  - annotated EPUB
- Optional Chinese dictionary definitions are supported.
- Chinese UI exists; English UI also exists.
- The app shows a reading-fit estimate from coverage, but it is explicitly approximate because the known-word source is frequency-based.
- Annotated EPUB supports two configurable annotation styles:
  - inline definitions (checkbox)
  - end-of-chapter note references + note list (checkbox)
  - both are enabled by default

## Important user preferences

- Keep the browser title as `BookVocab APP`.
- Use a Chinese page header in the app body.
- Keep the interface simple and learner-friendly.
- No page-number mode; EPUB page numbers are not reliable across readers.
- Chapter-based filtering is preferred.
- Keep the context/details visible, but avoid cluttering the table.
- Keep the annotated EPUB flow as generate-then-download, with visible progress/ready feedback.
- Avoid extra captions unless they add real value.
- Chinese definitions should be optional, not forced for English users.

## Current UI / behavior decisions

- Language toggle is shown near the top of the page (outside the sidebar).
- The sidebar contains:
  - known vocabulary size
  - cleanup filters
  - Chinese definition toggle
  - front-matter toggle
  - frequency toggle
  - annotation settings (two checkboxes: inline definitions, end-of-chapter notes)
  - optional known-word list
- The previous floating overlay hack was removed because it was fragile.
- The project currently keeps the chapter view only; no page-range feature.
- The annotated EPUB export uses the current filtered unknown-word list, not every word in the book.
- Annotation settings are placed below cleanup filters and above optional known-word upload.
- When no valid upload is loaded yet, the UI shows a retry hint for transient upload failures (including occasional `400`).

## Repo structure

- `app.py` - main Streamlit app
- `epub_analyzer.py` - EPUB parsing, tokenization, unknown-word analysis, known-word application
- `deploy.sh` - Azure Container Registry build + Azure Container App update
- `run.sh` - local Streamlit launch script
- `requirements.txt` - Python dependencies
- `README.md` - setup and deployment summary
- `dump_known_words.py` - helper script for inspecting known-word normalization
- `known_words_top12000.txt` - dumped normalized top-12000 word list

## Deployment

Current deployment target is Azure:

- Azure Container Registry: `bookvocab.azurecr.io`
- Azure Container App: `bookvocabapp`
- Resource group: `book_vocab`

`deploy.sh` builds a new image tag from the git SHA, pushes to ACR, and updates the container app.

## Known implementation details

- `app.py` uses Streamlit session state heavily.
- `translate_word_to_zh()` is cached.
- Annotated EPUB export is generated in-memory and stored in session state.
- The EPUB export uses the source EPUB structure and appends `BookVocab version` to the title/export name.
- Annotated EPUB now edits source HTML in-place (DOM-based annotation), instead of rewriting whole chapter pages as plain text.
- Export annotation behavior:
  - inline annotation uses Chinese text when Chinese definitions are enabled; otherwise English
  - end-of-chapter notes show `English | Chinese` when Chinese definitions are enabled; otherwise English only
  - each normalized word is annotated once per chapter/document
- For note compatibility, existing book footnote/noteref links are normalized to jump-link behavior and annotation skips note-related regions.
- EPUB export signature includes annotation settings + version to force regeneration after annotation logic changes.
- The app already includes user-friendly failure messages for upload/download/analysis problems.
- `streamlit` is pinned to `1.41.1`.
- The app depends on `beautifulsoup4`, `ebooklib`, `spacy`, `nltk`, `wordfreq`, `pandas`, and optional `cedict`.

## Important caveats

- EPUB page numbers are not stable across readers, so do not reintroduce page-based filtering unless there is a very good reason.
- The known-word source is frequency-list-based, so reading-fit and CEFR/IELTS mapping are only estimates.
- Chinese definition availability depends on the dictionary lookup; keep the English definition if Chinese is unavailable in the EPUB export, but do not show empty Chinese columns in the table.
- Be careful with Streamlit session-state widget rules. Setting a widget key after instantiation causes runtime errors.
- Avoid adding extra duplicate loading spinners or captions unless they solve a real UX issue.

## Current priorities / likely next work

- Keep the sidebar discoverable on mobile.
- Keep the main analysis page uncluttered.
- Preserve the current export flow and avoid regressions in:
  - Anki TSV
  - annotated EPUB
  - Chinese definition toggle
  - front matter filtering
- If changing the results table, keep the word order and context selection behavior intact.

## TODO

- Add regression tests for:
  - annotation setting combinations (inline/endnote on/off)
  - Chinese toggle effects on inline vs endnote text
  - original-book footnote jump behavior after export
- Validate exported EPUB behavior across readers (Apple Books / Kindle app / Kobo / Readium), especially note references.
- Add PDF extraction / PDF annotation support if the EPUB flow stabilizes.
- Revisit upload size limits; 100 MB may be a better ceiling if backend limits allow it.

## Known issues

- Occasional upload `400` errors still happen, although Azure sticky sessions reduced them.
- EPUB reader compatibility still varies by app/device, especially for note rendering details.
- Inline annotations can look dense for some books/readers; users can disable inline mode and keep endnotes only.

## Useful commands

```bash
./run.sh
./deploy.sh
```

For local validation:

```bash
PYTHONPYCACHEPREFIX=/tmp/.pycache .venv/bin/python -m py_compile app.py epub_analyzer.py
```
