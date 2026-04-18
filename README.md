# BookVocab

Streamlit app for EPUB vocabulary analysis.

It lets you:
- upload an `.epub`
- extract chapter text
- surface likely unknown words
- hide noisy tokens and front matter
- browse results by chapter range
- export JSON or CSV

## Run locally

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m spacy download en_core_web_sm
.venv/bin/python -m nltk.downloader wordnet omw-1.4
./run.sh
```

## Live Demo

Live app: `YOUR_DEPLOYED_URL_HERE`

## Notes

- EPUB page numbers are not reliable across readers, so this app focuses on chapter-based analysis.
- The app uses lemma-based normalization and WordNet definitions to help English learners review vocabulary.
- Uploaded EPUB files are processed locally by the app.
