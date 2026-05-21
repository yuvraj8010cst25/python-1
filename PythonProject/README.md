# LoanCheck Python

LoanCheck is now a Python-first loan eligibility calculator web app for the India market.

## What It Includes

- Flask web app with six loan pages:
  - `/home-loan`
  - `/personal-loan`
  - `/car-loan`
  - `/lap`
  - `/education-loan`
  - `/business-loan`
- Python eligibility engine in `loancheck/engine.py`
- Python loan product configuration and FAQs in `loancheck/config.py`
- Tailwind-styled responsive templates served by Flask
- Multi-step form, live results, EMI breakdown, amortisation table, compare mode, EMI, balance transfer and affordability tools
- Shareable URL, WhatsApp share, print-friendly results and expert modal
- Unit tests with pytest
- Cached `/api/bank-rates` endpoint for current lender-rate comparison across all six loan products

## Run The Python App

Install Python 3.10 or newer from:

```text
https://www.python.org/downloads/
```

During installation, tick **Add python.exe to PATH**.

Create and activate a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the app:

```bash
python run.py
```

Open:

```text
http://127.0.0.1:5000/home-loan
```

## Run Tests

```bash
pytest
```

## Deploy On Render

Use Render as a Python web service, not as a static site.

```text
Build Command:
pip install -r requirements.txt

Start Command:
gunicorn run:app
```

Do not rename `loancheck/templates/calculator.html` to `index.html`. Flask renders that template through Python routes.

## One File Version

If you want to explain or demo the full app from one Python file, use:

```bash
python single_file_full_app.py
```

It contains the Flask routes, eligibility engine, bank-rate API, fallback rate data, and HTML/JavaScript UI in one file. The modular production version is still the recommended version for long-term editing.

## Bank Rate API

Every loan page calls:

```text
GET /api/bank-rates?loanType=home
GET /api/bank-rates?loanType=personal&refresh=true
```

Supported `loanType` values are `home`, `lap`, `personal`, `car`, `education`, and `business`.

The endpoint fetches public rate pages where available, parses rates with BeautifulSoup, caches each product response for six hours, and falls back to built-in rates if scraping fails.

## Notes

The old Next.js files are still present from the first version, but the Python app lives in:

```text
loancheck/
run.py
requirements.txt
tests/
```
