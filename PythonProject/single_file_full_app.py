"""Presentation entry point for the original LoanCheck app.

Important:
The polished UI lives in the modular Flask project:
- loancheck/app.py
- loancheck/templates/calculator.html
- loancheck/static/js/app.js
- loancheck/static/css/app.css

This file intentionally launches that original app so the UI does not change.
Use this command for demo/presentation:

    python single_file_full_app.py
"""

from loancheck.app import app


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
