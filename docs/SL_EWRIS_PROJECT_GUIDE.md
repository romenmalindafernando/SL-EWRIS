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
- Neon PostgreSQL via psycopg 3
- Statistical analysis in R
- Scikit-learn (where applicable)
- Git / GitHub

### Implemented Prototype Features

- Historical economic data exploration
- Monthly economic data entry
- Neon-backed draft storage
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

Raw CBSL/DCS workbooks, local SQLite backups
and generated research outputs may be excluded
from the public repository.

The application may require locally prepared datasets.
Some pages will display unavailable-data warnings
until the corresponding source files have been generated.

Do not fabricate missing official observations.

## Neon and Render deployment

The application reads the PostgreSQL connection string only from the
`DATABASE_URL` environment variable. Create a Neon project and copy its pooled
connection string (including SSL settings) into Render's service environment;
do not place it in source control, Streamlit secrets, logs, or screenshots.

Install dependencies with `pip install -r requirements.txt`, then start the
service with `python -m streamlit run app.py --server.address 0.0.0.0
--server.port $PORT`. The first connection applies additive, idempotent schema
migrations. It never drops, truncates, resets, or overwrites rows.

If an existing local database must be moved once, keep the original file and
run `python migrate_sqlite_to_postgres.py path\to\economic_risk.db --dry-run`
first. Review the row counts, then rerun without `--dry-run`; the script writes
a timestamped `.bak` copy before destination writes and inserts only missing
primary keys.

### Safe initial Neon setup

From the repository root in PowerShell, with `DATABASE_URL` already set in the
environment:

```powershell
.\.venv\Scripts\python.exe -c "from database import connect_database; connection = connect_database(); connection.commit(); connection.close()"
.\.venv\Scripts\python.exe seed_database.py
```

The first command creates the five application tables plus the
`schema_migrations` bookkeeping table. The second validates and imports the
144 rows from `data\historical_data.csv`. It uses `ON CONFLICT (month) DO
NOTHING`, so rerunning it does not overwrite existing observations.

Verify without modifying data:

```powershell
.\.venv\Scripts\python.exe -c "from database import connect_database; connection = connect_database(); print(connection.execute('SELECT COUNT(*) FROM economic_monthly').fetchone()[0]); print(connection.execute('SELECT MIN(month), MAX(month) FROM economic_monthly').fetchone()); connection.rollback(); connection.close()"
```

For a direct SQL check in Neon, run:

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

SELECT COUNT(*) AS historical_rows,
       COUNT(*) FILTER (WHERE headline_yoy_pct IS NULL) AS null_headline_rows
FROM economic_monthly;

SELECT MIN(month) AS first_month, MAX(month) AS last_month
FROM economic_monthly;
```

The seed operation is one transaction: schema creation and inserts are
committed together. If validation or insertion fails, the uncommitted
transaction is rolled back when the connection closes. No production write
should be run until the dry-run counts and target database are confirmed.

For Render Free (512 MB), use the existing bounded Streamlit data cache where
appropriate, avoid loading raw source workbooks in the web process, and run
heavy model training/import jobs as one-off jobs rather than on every page
render. The custom cloud frontend uses a bounded data cache and a direct
cursor fetch to avoid reconnecting to Neon on every rerun and to keep the
PostgreSQL adapter supported. Neon should be configured with a pooled
connection string and the smallest practical compute tier.

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
