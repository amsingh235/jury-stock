# Sources to download

Every note in `knowledge/raw/<collection>/placeholder_notes.md` is a placeholder summary,
indexed with `secondary_source: true` and `placeholder: true`. Secondary sources get a
1.15x distance penalty at retrieval, so real texts outrank them.

## Automatic download (14 legal free full texts)

`config/sources_manifest.yaml` lists 12 canon papers and 2 public-domain books, all from author
pages, NBER, arXiv, the St. Louis Fed, a university repository or Project Gutenberg. Run:

```
venv/Scripts/python backend/scripts/fetch_sources.py
venv/Scripts/python backend/scripts/build_kb.py
```

The script verifies each file, saves it here, and removes the placeholder note it replaces.
Downloaded files are git-ignored: this repo is public, and the papers are not ours to redistribute.

## Replacing a placeholder with the real source (manually)

1. Get a legitimate copy of the work as a PDF.
2. Name it `Author_Year_Title.pdf` (e.g. `Piotroski_2000_Value_Investing.pdf`).
   Author, year and title are read from the filename; PDFs are indexed with
   `secondary_source: false`.
3. Put it in the same `knowledge/raw/<collection>/` folder.
4. Delete that note's block (from its `---` frontmatter up to the next `---`) from
   `placeholder_notes.md`, so the work isn't indexed twice.
5. Rebuild: `venv/Scripts/python backend/scripts/build_kb.py`.

## Where to look (spec §3.1, §13)

- Papers: arXiv, SSRN, Google Scholar, authors' own sites. Search terms per collection are in spec §13.
- Public-domain books, load in full: *Reminiscences of a Stock Operator* (Lefevre, 1923) and
  *The Psychology of Speculation* (Hoyle, 1902). These go in `contrarian/` or `chart/`.
- Copyrighted books (Graham, Damodaran, Murphy, Bulkowski, Kahneman, Taleb...): publisher excerpts,
  author summaries, lecture notes, or short fair-use quotations only. Never pirated PDFs.
  If no legal full text exists, keep the placeholder note.

## Current placeholders (57)

| Collection | Author | Year | Title |
|---|---|---|---|
| chart | Edwards and Magee | 1948 | Technical Analysis of Stock Trends |
| chart | Murphy | 1999 | Technical Analysis of the Financial Markets |
| chart | Bulkowski | 2005 | Encyclopedia of Chart Patterns |
| chart | Bulkowski | 2008 | Encyclopedia of Candlestick Charts |
| chart | Park and Irwin | 2007 | What Do We Know About the Profitability of Technical Analysis? |
| chart | Brock, Lakonishok and LeBaron | 1992 | Simple Technical Trading Rules and the Stochastic Properties of Stock Returns |
| chart | Lo, Mamaysky and Wang | 2000 | Foundations of Technical Analysis |
| chart | Neely, Rapach, Tu and Zhou | 2014 | Forecasting the Equity Risk Premium: The Role of Technical Indicators |
| chart | Wilder | 1978 | New Concepts in Technical Trading Systems |
| chart | Appel; Arditti | 1979 | MACD and Volume-Price Confirmation |
| contrarian | Kahneman | 2011 | Thinking, Fast and Slow |
| contrarian | Shiller | 2000 | Irrational Exuberance |
| contrarian | Taleb | 2001 | Fooled by Randomness |
| contrarian | Barber and Odean | 2000 | Trading Is Hazardous to Your Wealth |
| contrarian | Barber and Odean | 2001 | Boys Will Be Boys: Gender, Overconfidence, and Common Stock Investment |
| contrarian | Scharfstein and Stein | 1990 | Herd Behavior and Investment |
| contrarian | Shefrin and Statman | 1985 | The Disposition to Sell Winners Too Early and Ride Losers Too Long |
| contrarian | Sullivan, Timmermann and White | 1999 | Data-Snooping, Technical Trading Rule Performance, and the Bootstrap |
| contrarian | Brown, Goetzmann, Ibbotson and Ross | 1992 | Survivorship Bias in Performance Studies |
| contrarian | Taleb | 2007 | The Black Swan |
| fundamentals | Graham and Dodd | 1934 | Security Analysis |
| fundamentals | Buffett | 1977 | Berkshire Hathaway Shareholder Letters |
| fundamentals | Damodaran | 2012 | Damodaran on Valuation (lecture notes) |
| fundamentals | Piotroski | 2000 | Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers |
| fundamentals | Novy-Marx | 2013 | The Other Side of Value: The Gross Profitability Premium |
| fundamentals | Sloan | 1996 | Do Stock Prices Fully Reflect Information in Accruals and Cash Flows about Future Earnings? |
| fundamentals | Altman | 1968 | Financial Ratios, Discriminant Analysis and the Prediction of Corporate Bankruptcy |
| fundamentals | Mohanram | 2005 | Separating Winners from Losers among Low Book-to-Market Stocks |
| fundamentals | Lakonishok, Shleifer and Vishny | 1994 | Contrarian Investment, Extrapolation, and Risk |
| fundamentals | Fama and French | 1992 | The Cross-Section of Expected Stock Returns |
| news | Fama, Fisher, Jensen and Roll | 1969 | The Adjustment of Stock Prices to New Information |
| news | Bernard and Thomas | 1989 | Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium? |
| news | Ikenberry, Lakonishok and Vermaelen | 1995 | Market Underreaction to Open Market Share Repurchases |
| news | Jenter | 2005 | Market Timing and Managerial Portfolio Decisions |
| news | Stickel; Gleason and Lee | 2003 | Analyst Forecast Revisions and Stock Returns |
| news | Pound and Zeckhauser | 1990 | Takeover Rumors and Price Effects |
| news | Bernanke and Kuttner | 2005 | What Explains the Stock Market's Reaction to Federal Reserve Policy? |
| news | Various (RBI studies) | 2015 | Monetary Policy Announcements and Indian Equity Markets |
| news | Stangl, Jacobsen and Visaltanachoti | 2009 | Sector Rotation over Business Cycles |
| quant | Jegadeesh and Titman | 1993 | Returns to Buying Winners and Selling Losers |
| quant | Asness, Moskowitz and Pedersen | 2013 | Value and Momentum Everywhere |
| quant | Fama and French | 1993 | Common Risk Factors in the Returns on Stocks and Bonds |
| quant | Carhart | 1997 | On Persistence in Mutual Fund Performance |
| quant | Novy-Marx | 2012 | Is Momentum Really Momentum? |
| quant | Frazzini and Pedersen | 2014 | Betting Against Beta |
| quant | Lehmann | 1990 | Fads, Martingales, and Market Efficiency |
| quant | George and Hwang | 2004 | The 52-Week High and Momentum Investing |
| quant | Moskowitz, Ooi and Pedersen | 2012 | Time Series Momentum |
| sentiment | Loughran and McDonald | 2011 | When Is a Liability Not a Liability? Textual Analysis, Dictionaries, and 10-Ks |
| sentiment | Araci | 2019 | FinBERT: Financial Sentiment Analysis with Pre-trained Language Models |
| sentiment | Bollen, Mao and Zeng | 2011 | Twitter Mood Predicts the Stock Market |
| sentiment | Tetlock | 2007 | Giving Content to Investor Sentiment: The Role of Media in the Stock Market |
| sentiment | Antweiler and Frank | 2004 | Is All That Talk Just Noise? The Information Content of Internet Stock Message Boards |
| sentiment | Da, Gurun and Warachka | 2014 | Frog in the Pan: Continuous Information and Momentum |
| sentiment | Da, Engelberg and Gao | 2011 | In Search of Attention |
| sentiment | Da, Engelberg and Gao | 2015 | The Sum of All FEARS: Investor Sentiment and Asset Prices |
| sentiment | Fang and Peress | 2009 | News Momentum and Media Coverage |
