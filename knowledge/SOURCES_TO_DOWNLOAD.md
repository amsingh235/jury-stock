# Sources to download

Every note in `knowledge/raw/<collection>/placeholder_notes.md` is a placeholder summary,
indexed with `secondary_source: true` and `placeholder: true`. Secondary sources get a
1.15x distance penalty at retrieval, so real texts outrank them.

## Replacing a placeholder with the real source

1. Get a legitimate copy of the work as a PDF.
2. Name it `Author_Year_Title.pdf` (e.g. `Graham_1949_The_Intelligent_Investor.pdf`).
   Author, year and title are read from the filename; PDFs are indexed with
   `secondary_source: false`.
3. Put it in the same `knowledge/raw/<collection>/` folder.
4. Delete that note's block (from its `---` frontmatter up to the next `---`) from
   `placeholder_notes.md`, so the work isn't indexed twice.
5. Rebuild: `venv/Scripts/python backend/scripts/build_kb.py`.

## Current placeholders

| Collection | Author | Year | Title |
|---|---|---|---|
| value | Graham | 1949 | The Intelligent Investor |
| value | Graham and Dodd | 1934 | Security Analysis |
| growth | Fisher | 1958 | Common Stocks and Uncommon Profits |
| growth | Lynch | 1989 | One Up On Wall Street |
| technical | Murphy | 1999 | Technical Analysis of the Financial Markets |
| technical | O'Neil | 1988 | How to Make Money in Stocks |
| macro | Dalio | 2018 | Principles for Navigating Big Debt Crises |
| macro | Kindleberger | 1978 | Manias, Panics, and Crashes |
| risk | Poundstone | 2005 | Fortune's Formula |
| risk | Bernstein | 1996 | Against the Gods |
| contrarian | Dreman | 1998 | Contrarian Investment Strategies |
| contrarian | Marks | 2011 | The Most Important Thing |
