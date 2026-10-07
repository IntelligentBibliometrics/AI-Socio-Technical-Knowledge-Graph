# AI Socio-Technical Knowledge Graph
Code for constructing an AI-focused socio-technical knowledge graph that links academic grant proposals, scientific publications, patents, policy documents, news, and tweets across the United States, the United Kingdom, the European Union, and Australia.

The resulting dataset (1,442,023 entities across 10 node tables and 98,870,658 relationships across 15 edge tables) is openly available on Kaggle:
**https://doi.org/10.34740/kaggle/ds/11349559**
Archived version: https://doi.org/10.5281/zenodo.23213724

## Schema

<img width="1495" height="1766" alt="Untitled (3)" src="https://github.com/user-attachments/assets/90365c00-2083-4c3c-8104-9d5af0bb758c" />

## Pipeline

The code follows the three-step workflow described in the paper:

- **`collection/`** — Retrieval scripts for each source (OpenAlex, NSF, ARC, CORDIS, UKRI, USPTO/EPO/IP Australia, GOV.UK, US Federal Register, EUR-Lex, APO, and X).
- **`preprocessing/`** — Source-specific cleaning, GPT-based classification of AI-related grants, named entity recognition (AIONER, BERT-Large, SciBERT), and institution disambiguation.
- **`linking/`** — Cross-source linking: DOI-based identifier matching, BM25-scored entity-based linkage, and country mapping; paper-to-paper citations within the corpus (`04_paper_citations.py`); and retrieval of the datasets and software associated with papers from the OpenAIRE Graph by DOI (`05_openaire_links.py`).

## Citation

Wang, T., Wu, M. & Zhang, Y. AI Socio-Technical Knowledge Graph. *Kaggle* https://doi.org/10.34740/kaggle/ds/11349559 (2026).

## License

Released under the MIT License. See [LICENSE](LICENSE).
