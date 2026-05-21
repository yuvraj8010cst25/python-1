from __future__ import annotations

import base64
import json
from urllib.parse import unquote
from dataclasses import asdict
from typing import Optional

from flask import Flask, jsonify, redirect, render_template, request, url_for

from .bank_rates import get_bank_rates
from .config import FAQS, LOAN_CONFIGS
from .engine import (
    EligibilityInput,
    calculate_balance_transfer_savings,
    calculate_eligibility,
    loan_from_emi,
)
from .formatters import format_compact_inr, format_inr


def create_app() -> Flask:
    app = Flask(__name__)

    @app.template_filter("inr")
    def _inr(value: float) -> str:
        return format_inr(value)

    @app.template_filter("compact_inr")
    def _compact_inr(value: float) -> str:
        return format_compact_inr(value)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/<slug>")
    def loan_page(slug: str):
        loan_type = _type_from_slug(slug)
        if not loan_type:
            return redirect(url_for("loan_page", slug="home-loan"))
        config = LOAN_CONFIGS[loan_type]
        initial = EligibilityInput(loan_type=loan_type)
        encoded_state = request.args.get("state")
        if encoded_state:
            initial = _decode_state(encoded_state, fallback=initial)
            initial.loan_type = loan_type
        result = calculate_eligibility(initial)
        schema = {
            "@context": "https://schema.org",
            "@type": "FinancialProduct",
            "name": f"{config.label} Eligibility Calculator",
            "provider": {"@type": "Organization", "name": "LoanCheck"},
            "category": "Loan calculator",
            "offers": {"@type": "Offer", "priceCurrency": "INR"},
        }
        return render_template(
            "calculator.html",
            active_type=loan_type,
            configs=LOAN_CONFIGS,
            config=config,
            faqs=FAQS[loan_type],
            initial=asdict(initial),
            initial_json=json.dumps(asdict(initial)),
            result=result,
            result_json=json.dumps(result),
            configs_json=json.dumps({key: asdict(value) for key, value in LOAN_CONFIGS.items()}),
            faqs_json=json.dumps(FAQS),
            schema=json.dumps(schema),
        )

    @app.post("/api/calculate")
    def api_calculate():
        input_data = EligibilityInput.from_mapping(request.get_json(silent=True) or {})
        result = calculate_eligibility(input_data)
        return jsonify({"input": asdict(input_data), "result": result})

    @app.post("/api/balance-transfer")
    def api_balance_transfer():
        payload = request.get_json(silent=True) or {}
        savings = calculate_balance_transfer_savings(
            outstanding=float(payload.get("outstanding", 2_500_000)),
            current_rate=float(payload.get("current_rate", 11)),
            new_rate=float(payload.get("new_rate", 9.5)),
            remaining_years=int(float(payload.get("remaining_years", 10))),
            processing_fee=float(payload.get("processing_fee", 10_000)),
        )
        return jsonify(savings)

    @app.post("/api/affordability")
    def api_affordability():
        payload = request.get_json(silent=True) or {}
        amount = loan_from_emi(
            emi=float(payload.get("emi", 50_000)),
            annual_rate=float(payload.get("annual_rate", 9)),
            tenure_years=int(float(payload.get("tenure_years", 20))),
        )
        return jsonify({"amount": amount})

    @app.get("/api/bank-rates")
    def api_bank_rates():
        force_refresh = request.args.get("refresh", "").lower() in {"1", "true", "yes"}
        loan_type = request.args.get("loanType", "home")
        response = jsonify(get_bank_rates(loan_type=loan_type, force_refresh=force_refresh))
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    return app


def _type_from_slug(slug: str) -> Optional[str]:
    for loan_type, config in LOAN_CONFIGS.items():
        if config.slug == slug:
            return loan_type
    return None


def _decode_state(encoded: str, fallback: EligibilityInput) -> EligibilityInput:
    try:
        raw = unquote(base64.urlsafe_b64decode(encoded.encode("utf-8")).decode("utf-8"))
        return EligibilityInput.from_mapping(json.loads(raw))
    except (ValueError, json.JSONDecodeError):
        return fallback


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
