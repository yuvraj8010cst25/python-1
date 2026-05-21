"""Compatibility launcher for the original LoanCheck UI.

The full app is intentionally kept in the `loancheck/` package:
- loancheck/app.py contains the Flask routes
- loancheck/templates/calculator.html contains the original polished UI
- loancheck/static/js/app.js contains the live calculator and bank-rate widget

Run this file if you want a single obvious entry point:
    python all_in_one_app.py
"""

from loancheck.app import app


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
