# SL-EWRIS
## Sri Lanka Economic Warning & Risk Intelligence System

### Project Overview

SL-EWRIS is an academic economic monitoring and research
prototype focused on Sri Lanka.

The system combines historical economic indicators,
monthly data management, statistical analysis,
retrospective stress screening and visual dashboards.

### Research Objectives

1. Analyze inflation and purchasing power trends.
2. Examine nominal and real wage changes.
3. Monitor exchange rates and foreign reserves.
4. Identify historical economic stress patterns.
5. Evaluate preliminary economic warning indicators.
6. Investigate publication-aware historical validation.

### Technology Stack

- Python
- Streamlit
- Pandas / NumPy
- SQLite
- Statistical analysis in R
- Scikit-learn (where applicable)
- Git / GitHub

### Implemented Prototype Features

- Historical economic data exploration
- Monthly economic data entry
- SQLite draft storage
- Indicator-level manual review
- Data quality monitoring
- Retrospective external-sector analysis
- Preliminary economic pressure score
- Threshold sensitivity analysis
- Historical lead-time exploration
- Point-in-time evidence framework
- Historical publication evidence tracking

### Local Installation

1. Install Python and Git.
2. Clone the repository.
3. Open a terminal in Python_Economic_Risk.
4. Create a virtual environment:

   python -m venv .venv

5. Activate it in Windows PowerShell:

   .\.venv\Scripts\Activate.ps1

6. Install dependencies:

   python -m pip install -r requirements.txt

7. Start Streamlit:

   python -m streamlit run app.py

### Data Setup

Raw CBSL/DCS workbooks, local SQLite databases
and generated research outputs may be excluded
from the public repository.

The application may require locally prepared datasets.
Some pages will display unavailable-data warnings
until the corresponding source files have been generated.

Do not fabricate missing official observations.

### Important Research Limitations

This project is currently a monitoring and
retrospective risk-screening prototype.

Its preliminary pressure score is NOT a financial-crisis
probability.

Historical publication dates and data vintages
are not yet fully verified.

Crisis-warning predictive accuracy, false-alarm rates
and generalization performance have not been established.

### Recommended Validation Before Final Submission

- Source publication and definition verification
- Point-in-time historical reconstruction
- Crisis event labeling
- Out-of-sample testing
- False-alarm and missed-event analysis
- Threshold sensitivity and robustness analysis
- Full application integration testing

### Academic Use

Developed as a Statistics and Computer Science
capstone research project focused on the
Sri Lankan economic environment.
