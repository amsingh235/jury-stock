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

## Full texts in the download list (24)

| Collection | File | Source |
|---|---|---|
| fundamentals | `Lakonishok_1994_Contrarian_Investment_Extrapolation_and_Risk.pdf` | NBER WP 4360 (1993), published J. Finance 1994 |
| fundamentals | `Novy-Marx_2013_The_Other_Side_of_Value.pdf` | NBER WP 15940 (2010), earlier draft of the 2013 JFE paper |
| quant | `Asness_2013_Value_and_Momentum_Everywhere.pdf` | published version, Pedersen's NYU page |
| quant | `Moskowitz_2012_Time_Series_Momentum.pdf` | Pedersen's NYU page; link not confirmed live |
| quant | `Frazzini_2014_Betting_Against_Beta.pdf` | published JFE version, CBS repository (CC BY-NC-ND) |
| chart | `Lo_2000_Foundations_of_Technical_Analysis.pdf` | NBER WP 7613 (2000) |
| chart | `Neely_2014_Forecasting_the_Equity_Risk_Premium_Technical_Indicators.pdf` | St. Louis Fed WP 2010-008H (rev. 2013) |
| sentiment | `Bollen_2011_Twitter_Mood_Predicts_the_Stock_Market.pdf` | arXiv 1010.3003 |
| sentiment | `Araci_2019_FinBERT_Financial_Sentiment_Analysis.pdf` | arXiv 1908.10063 |
| sentiment | `Tetlock_2007_Giving_Content_to_Investor_Sentiment.pdf` | author's Columbia page |
| news | `Bernanke_2005_Stock_Market_Reaction_to_Federal_Reserve_Policy.pdf` | NBER WP 10402 (2004), published J. Finance 2005 |
| contrarian | `Barber_2001_Boys_Will_Be_Boys.pdf` | Odean's Berkeley page |
| contrarian | `Lefevre_1923_Reminiscences_of_a_Stock_Operator.txt` | public domain (Project Gutenberg no. 60979), spec §13 |
| contrarian | `Harper_1926_The_Psychology_of_Speculation.txt` | public domain (Project Gutenberg no. 73647). Spec §13 names Hoyle (1902); no free copy of Hoyle was found, so this is Harper's book of the same title. |
| fundamentals | `Campbell_2008_In_Search_of_Distress_Risk.pdf` | NBER WP 12362 |
| quant | `Hou_2015_Digesting_Anomalies.pdf` | NBER WP 18435 |
| quant | `Daniel_2016_Momentum_Crashes.pdf` | NBER WP 20439 |
| quant | `Ang_2006_Cross-Section_of_Volatility_and_Expected_Returns.pdf` | NBER WP 10852 |
| quant | `Harvey_2016_and_the_Cross-Section_of_Expected_Returns.pdf` | NBER WP 20592 |
| sentiment | `Baker_2006_Investor_Sentiment_and_the_Cross-Section.pdf` | NBER WP 10449 |
| news | `Chan_1996_Momentum_Strategies.pdf` | NBER WP 5375 |
| news | `Cohen_2012_Decoding_Inside_Information.pdf` | NBER WP 16454 |
| contrarian | `Shleifer_1997_The_Limits_of_Arbitrage.pdf` | NBER WP 5167 |
| contrarian | `Odean_1998_Are_Investors_Reluctant_to_Realize_Their_Losses.pdf` | author's Berkeley page |

Rejected by the verifier and kept as placeholders: Chan, Jegadeesh and Lakonishok (1996) and
Shleifer and Vishny (1997). Their NBER copies are scans whose text layer is unreadable. The two
NYU-hosted papers (Asness 2013, Moskowitz 2012) also need `w4.stern.nyu.edu` to be reachable.

## Current placeholders (64)

| Collection | Author | Year | Title |
|---|---|---|---|
| chart | Edwards and Magee | 1948 | Technical Analysis of Stock Trends |
| chart | Murphy | 1999 | Technical Analysis of the Financial Markets |
| chart | Bulkowski | 2005 | Encyclopedia of Chart Patterns |
| chart | Bulkowski | 2008 | Encyclopedia of Candlestick Charts |
| chart | Park and Irwin | 2007 | What Do We Know About the Profitability of Technical Analysis? |
| chart | Brock, Lakonishok and LeBaron | 1992 | Simple Technical Trading Rules and the Stochastic Properties of Stock Returns |
| chart | Wilder | 1978 | New Concepts in Technical Trading Systems |
| chart | Appel; Arditti | 1979 | MACD and Volume-Price Confirmation |
| chart | Marshall, Young and Rose | 2006 | Candlestick Technical Trading Strategies: Can They Create Value for Investors? |
| chart | Lu, Shiu and Liu | 2012 | Pattern Recognition and Candlestick Profitability in Taiwan |
| chart | Caginalp and Laurent | 1998 | The Predictive Power of Price Patterns |
| chart | Han, Yang and Zhou | 2013 | A New Anomaly: The Cross-Sectional Profitability of Technical Analysis |
| chart | Zhu and Zhou | 2009 | Technical Analysis: An Asset Allocation Perspective on the Use of Moving Averages |
| contrarian | Kahneman | 2011 | Thinking, Fast and Slow |
| contrarian | Shiller | 2000 | Irrational Exuberance |
| contrarian | Taleb | 2001 | Fooled by Randomness |
| contrarian | Barber and Odean | 2000 | Trading Is Hazardous to Your Wealth |
| contrarian | Scharfstein and Stein | 1990 | Herd Behavior and Investment |
| contrarian | Shefrin and Statman | 1985 | The Disposition to Sell Winners Too Early and Ride Losers Too Long |
| contrarian | Sullivan, Timmermann and White | 1999 | Data-Snooping, Technical Trading Rule Performance, and the Bootstrap |
| contrarian | Brown, Goetzmann, Ibbotson and Ross | 1992 | Survivorship Bias in Performance Studies |
| contrarian | Taleb | 2007 | The Black Swan |
| contrarian | De Bondt and Thaler | 1985 | Does the Stock Market Overreact? |
| contrarian | Shleifer and Vishny | 1997 | The Limits of Arbitrage |
| fundamentals | Graham and Dodd | 1934 | Security Analysis |
| fundamentals | Buffett | 1977 | Berkshire Hathaway Shareholder Letters |
| fundamentals | Damodaran | 2012 | Damodaran on Valuation (lecture notes) |
| fundamentals | Piotroski | 2000 | Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers |
| fundamentals | Sloan | 1996 | Do Stock Prices Fully Reflect Information in Accruals and Cash Flows about Future Earnings? |
| fundamentals | Altman | 1968 | Financial Ratios, Discriminant Analysis and the Prediction of Corporate Bankruptcy |
| fundamentals | Mohanram | 2005 | Separating Winners from Losers among Low Book-to-Market Stocks |
| fundamentals | Fama and French | 1992 | The Cross-Section of Expected Stock Returns |
| fundamentals | Asness, Frazzini and Pedersen | 2019 | Quality Minus Junk |
| fundamentals | Beneish | 1999 | The Detection of Earnings Manipulation |
| news | Fama, Fisher, Jensen and Roll | 1969 | The Adjustment of Stock Prices to New Information |
| news | Bernard and Thomas | 1989 | Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium? |
| news | Ikenberry, Lakonishok and Vermaelen | 1995 | Market Underreaction to Open Market Share Repurchases |
| news | Jenter | 2005 | Market Timing and Managerial Portfolio Decisions |
| news | Stickel; Gleason and Lee | 2003 | Analyst Forecast Revisions and Stock Returns |
| news | Pound and Zeckhauser | 1990 | Takeover Rumors and Price Effects |
| news | Various (RBI studies) | 2015 | Monetary Policy Announcements and Indian Equity Markets |
| news | Stangl, Jacobsen and Visaltanachoti | 2009 | Sector Rotation over Business Cycles |
| news | Ball and Brown | 1968 | An Empirical Evaluation of Accounting Income Numbers |
| news | Chan, Jegadeesh and Lakonishok | 1996 | Momentum Strategies |
| news | Chan | 2003 | Stock Price Reaction to News and No-News: Drift and Reversal after Headlines |
| quant | Jegadeesh and Titman | 1993 | Returns to Buying Winners and Selling Losers |
| quant | Asness, Moskowitz and Pedersen | 2013 | Value and Momentum Everywhere |
| quant | Fama and French | 1993 | Common Risk Factors in the Returns on Stocks and Bonds |
| quant | Carhart | 1997 | On Persistence in Mutual Fund Performance |
| quant | Novy-Marx | 2012 | Is Momentum Really Momentum? |
| quant | Lehmann | 1990 | Fads, Martingales, and Market Efficiency |
| quant | George and Hwang | 2004 | The 52-Week High and Momentum Investing |
| quant | Moskowitz, Ooi and Pedersen | 2012 | Time Series Momentum |
| quant | Amihud | 2002 | Illiquidity and Stock Returns: Cross-Section and Time-Series Effects |
| sentiment | Loughran and McDonald | 2011 | When Is a Liability Not a Liability? Textual Analysis, Dictionaries, and 10-Ks |
| sentiment | Antweiler and Frank | 2004 | Is All That Talk Just Noise? The Information Content of Internet Stock Message Boards |
| sentiment | Da, Gurun and Warachka | 2014 | Frog in the Pan: Continuous Information and Momentum |
| sentiment | Da, Engelberg and Gao | 2011 | In Search of Attention |
| sentiment | Da, Engelberg and Gao | 2015 | The Sum of All FEARS: Investor Sentiment and Asset Prices |
| sentiment | Fang and Peress | 2009 | News Momentum and Media Coverage |
| sentiment | Barber and Odean | 2008 | All That Glitters: The Effect of Attention and News on the Buying Behavior of Individual and Institutional Investors |
| sentiment | Garcia | 2013 | Sentiment during Recessions |
| sentiment | Huang, Jiang, Tu and Zhou | 2015 | Investor Sentiment Aligned: A Powerful Predictor of Stock Returns |
| sentiment | Chen, De, Hu and Hwang | 2014 | Wisdom of Crowds: The Value of Stock Opinions Transmitted Through Social Media |
