# EPUB Vocabulary Analyzer

Local Streamlit app for analyzing EPUB vocabulary by chapter, highlighting likely OOV words, and exporting the results.

## Run

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m spacy download en_core_web_sm
.venv/bin/python -m nltk.downloader wordnet omw-1.4
./run.sh
```
