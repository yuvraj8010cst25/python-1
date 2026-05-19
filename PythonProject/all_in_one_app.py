from __future__ import annotations

import base64
import json
import re
import time
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from math import ceil
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, redirect, render_template_string, request, url_for


app = Flask(__name__)


@dataclass(frozen=True)
class LoanConfig:
    type: str
    slug: str
    label: str
    min_rate: float
    max_rate: float
    base_rate: float
    max_tenure_years: int
    foir: float
    secured: bool
    ltv: Optional[float]


LOAN_CONFIGS = {
    "home": LoanConfig("home", "home-loan", "Home Loan", 8.5, 10, 9, 30, 0.50, True, 0.80),
    "lap": LoanConfig("lap", "lap", "Loan Against Property", 9.5, 11, 10.25, 20, 0.50, True, 0.65),
    "personal": LoanConfig("personal", "personal-loan", "Personal Loan", 11, 24, 14, 5, 0.45, False, None),
    "car": LoanConfig("car", "car-loan", "Car Loan", 9, 12, 10, 7, 0.48, True, 0.85),
    "education": LoanConfig("education", "education-loan", "Education Loan", 10.5, 13, 11.25, 15, 0.45, False, None),
    "business": LoanConfig("business", "business-loan", "Business Loan", 12, 18, 14.5, 10, 0.55, False, None),
}


@dataclass
class EligibilityInput:
    full_name: str = ""
    dob: str = "1992-01-01"
    gender: str = "male"
    employment_type: str = "salaried"
    monthly_income: float = 95_000
    other_income: float = 0
    existing_emis: float = 10_000
    dependants: int = 1
    cibil: int = 760
    has_co_applicant: bool = False
    co_applicant_income: float = 0
    co_applicant_cibil: int = 750
    loan_type: str = "home"
    property_value: float = 8_500_000
    preferred_tenure_years: int = 20
    rate_type: str = "floating"

    @classmethod
    def from_mapping(cls, payload: dict) -> "EligibilityInput":
        data = asdict(cls())
        for key in data:
            if key in payload:
                data[key] = payload[key]
        for key in ["monthly_income", "other_income", "existing_emis", "co_applicant_income", "property_value"]:
            data[key] = _num(data[key])
        for key in ["dependants", "cibil", "co_applicant_cibil", "preferred_tenure_years"]:
            data[key] = int(_num(data[key]))
        data["has_co_applicant"] = str(data["has_co_applicant"]).lower() in {"1", "true", "on", "yes"}
        data["loan_type"] = data["loan_type"] if data["loan_type"] in LOAN_CONFIGS else "home"
        return cls(**data)


def _num(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def age_from_dob(dob: str, as_of: Optional[date] = None) -> int:
    as_of = as_of or date.today()
    try:
        birth = datetime.strptime(dob, "%Y-%m-%d").date()
    except ValueError:
        return 0
    age = as_of.year - birth.year
    if (as_of.month, as_of.day) < (birth.month, birth.day):
        age -= 1
    return age


def emi_per_rupee(rate: float, years: int) -> float:
    months = max(1, years * 12)
    monthly = rate / 100 / 12
    if monthly == 0:
        return 1 / months
    factor = (1 + monthly) ** months
    return (monthly * factor) / (factor - 1)


def calculate(input_data: EligibilityInput) -> dict:
    cfg = LOAN_CONFIGS[input_data.loan_type]
    age = age_from_dob(input_data.dob)
    retirement_age = 60 if input_data.employment_type in {"salaried", "pensioner"} else 65
    max_tenure = int(clamp(min(cfg.max_tenure_years, max(1, retirement_age - age if age >= 21 else 1)), 1, cfg.max_tenure_years))
    tenure = int(clamp(input_data.preferred_tenure_years, 1, max_tenure))
    cibil = int(clamp(input_data.cibil, 300, 900))
    co_cibil = int(clamp(input_data.co_applicant_cibil, 300, 900))
    blended_cibil = round(cibil * 0.7 + co_cibil * 0.3) if input_data.has_co_applicant else cibil

    rate = cfg.base_rate + cibil_adjustment(blended_cibil)
    if input_data.gender == "female":
        rate -= 0.05
    if input_data.employment_type == "nri":
        rate += 0.25
    if input_data.employment_type == "professional":
        rate -= 0.10
    if input_data.rate_type == "fixed":
        rate += 0.35
    rate = clamp(rate, cfg.min_rate, cfg.max_rate + 3)

    income = max(0, input_data.monthly_income + input_data.other_income + (input_data.co_applicant_income if input_data.has_co_applicant else 0))
    adjusted_foir = clamp(cfg.foir - input_data.dependants * 0.015, 0.25, 0.60)
    available_emi = max(0, income * adjusted_foir - input_data.existing_emis)
    emi_factor = emi_per_rupee(rate, tenure)
    foir_loan = available_emi / emi_factor
    ltv_loan = input_data.property_value * cfg.ltv if cfg.ltv else None
    max_loan = max(0, min(foir_loan, ltv_loan if ltv_loan is not None else foir_loan))
    monthly_emi = max_loan * emi_factor
    total_interest = max(0, monthly_emi * tenure * 12 - max_loan)
    foir_ratio = (input_data.existing_emis + monthly_emi) / income if income else 1
    score = round(clamp(((blended_cibil - 300) / 600) * 35 + (1 - foir_ratio / 0.65) * 35 + age_score(age) * 0.20 + income_score(income) * 0.10, 0, 100))
    verdict = "Excellent - Apply Now" if score >= 82 else "Good" if score >= 68 else "Fair - Improve profile" if score >= 50 else "Low - Build credit first"

    return {
        "age": age,
        "max_loan": max_loan,
        "monthly_emi": monthly_emi,
        "interest_rate": rate,
        "total_interest": total_interest,
        "selected_tenure_years": tenure,
        "score": score,
        "verdict": verdict,
        "amortisation": [asdict(row) for row in amortisation(max_loan, rate, tenure)],
    }


def cibil_adjustment(cibil: int) -> float:
    if cibil >= 800:
        return -0.25
    if cibil >= 750:
        return 0
    if cibil >= 700:
        return 0.5
    if cibil >= 650:
        return 1
    return 2.5


def age_score(age: int) -> int:
    if age < 21 or age > 70:
        return 15
    if 25 <= age <= 45:
        return 100
    if age <= 55:
        return 80
    if age <= 62:
        return 55
    return 35


def income_score(income: float) -> int:
    if income >= 250_000:
        return 100
    if income >= 100_000:
        return 82
    if income >= 50_000:
        return 62
    if income >= 25_000:
        return 40
    return 20


@dataclass
class AmortisationRow:
    year: int
    principal: float
    interest: float
    closing_balance: float


def amortisation(principal: float, rate: float, years: int) -> List[AmortisationRow]:
    rows = []
    balance = principal
    emi = principal * emi_per_rupee(rate, years)
    monthly_rate = rate / 100 / 12
    for year in range(1, ceil(years * 12 / 12) + 1):
        principal_paid = 0.0
        interest_paid = 0.0
        for _ in range(12):
            if balance <= 0:
                break
            interest = balance * monthly_rate
            principal_component = min(balance, emi - interest)
            interest_paid += interest
            principal_paid += principal_component
            balance = max(0, balance - principal_component)
        rows.append(AmortisationRow(year, principal_paid, interest_paid, balance))
    return rows


def bank(name: str, salaried: float, self_emp: float, max_rate: float, processing: str, tenure: str, max_loan: str, tag: str) -> dict:
    return {"name": name, "salariedMin": salaried, "selfMin": self_emp, "minRate": min(salaried, self_emp), "maxRate": max_rate, "processing": processing, "tenure": tenure, "maxLoan": max_loan, "tag": tag, "isBest": False}


FALLBACK_RATES = {
    "home": [bank("SBI", 7.50, 7.65, 8.45, "0.35% + GST", "30 yrs", "No limit", "Strong public sector option"), bank("HDFC Bank", 7.90, 8.00, 9.15, "Up to 0.50% + GST", "30 yrs", "Case based", "Large private lender"), bank("ICICI Bank", 7.70, 7.85, 9.00, "Up to 0.50% + GST", "30 yrs", "Case based", "Fast private bank processing"), bank("Axis Bank", 8.35, 8.50, 9.15, "Up to 1% + GST", "30 yrs", "Up to Rs 5 Cr", "Flexible loan variants"), bank("Bank of Baroda", 7.20, 7.35, 9.25, "0.35% + GST", "30 yrs", "No limit", "Lowest public sector rate"), bank("IDBI Bank", 8.50, 8.65, 9.65, "0.50% + GST", "30 yrs", "Case based", "Simple salaried profile option")],
    "lap": [bank("SBI", 9.75, 9.90, 11.30, "1% + GST", "15 yrs", "Case based", "Stable public sector LAP"), bank("HDFC Bank", 9.50, 9.75, 11.50, "Up to 1% + GST", "15 yrs", "Case based", "Competitive LAP pricing"), bank("ICICI Bank", 9.60, 9.85, 11.75, "Up to 1% + GST", "15 yrs", "Case based", "Fast private bank processing"), bank("Axis Bank", 10.50, 10.75, 12.40, "Up to 1% + GST", "20 yrs", "Case based", "Longer LAP tenure"), bank("Bank of Baroda", 9.15, 9.35, 11.25, "0.50% + GST", "15 yrs", "Case based", "Public sector LAP value"), bank("IDBI Bank", 10.00, 10.25, 12.00, "1% + GST", "15 yrs", "Case based", "Simple property-backed loan")],
    "personal": [bank("SBI", 11.45, 11.70, 15.30, "Up to 1.50% + GST", "6 yrs", "Up to Rs 20 L", "Lower PSU personal loan rate"), bank("HDFC Bank", 10.85, 11.10, 24.00, "Up to Rs 6,500 + GST", "6 yrs", "Up to Rs 40 L", "Fast digital disbursal"), bank("ICICI Bank", 10.80, 11.05, 16.15, "Up to 2% + GST", "6 yrs", "Up to Rs 50 L", "Competitive private bank option"), bank("Axis Bank", 10.99, 11.25, 22.00, "Up to 2% + GST", "7 yrs", "Up to Rs 40 L", "Flexible tenure"), bank("Bank of Baroda", 10.90, 11.20, 18.25, "Up to 2% + GST", "7 yrs", "Up to Rs 20 L", "Public sector personal loan"), bank("IDBI Bank", 11.00, 11.30, 15.50, "1% + GST", "5 yrs", "Up to Rs 5 L", "Straightforward offer")],
    "car": [bank("SBI", 8.75, 8.90, 9.80, "0.25% + GST", "7 yrs", "Up to 90% on-road", "Strong car loan rate"), bank("HDFC Bank", 8.90, 9.10, 11.00, "Up to 1% + GST", "7 yrs", "Up to 100% ex-showroom", "Fast private bank option"), bank("ICICI Bank", 8.85, 9.05, 10.75, "Up to 1% + GST", "7 yrs", "Up to 100% ex-showroom", "Competitive car loan"), bank("Axis Bank", 9.10, 9.30, 12.00, "Up to 1% + GST", "7 yrs", "Up to 100% on-road", "Flexible car finance"), bank("Bank of Baroda", 8.70, 8.90, 10.25, "0.50% + GST", "7 yrs", "Up to 90% on-road", "Lowest car loan start"), bank("IDBI Bank", 9.00, 9.25, 10.50, "0.50% + GST", "7 yrs", "Up to 90% on-road", "Simple car loan option")],
    "education": [bank("SBI", 8.05, 8.20, 11.15, "As per scheme", "15 yrs", "Case based", "Popular education loan"), bank("HDFC Bank", 9.50, 9.75, 13.50, "Up to 1% + GST", "15 yrs", "Case based", "Private education finance"), bank("ICICI Bank", 9.85, 10.10, 13.75, "Up to 1% + GST", "10 yrs", "Case based", "Study loan option"), bank("Axis Bank", 10.50, 10.75, 15.00, "Up to 2% + GST", "15 yrs", "Case based", "Higher-ticket education loans"), bank("Bank of Baroda", 8.15, 8.35, 12.00, "As per scheme", "15 yrs", "Case based", "Public sector education loan"), bank("IDBI Bank", 9.20, 9.45, 12.75, "As per scheme", "15 yrs", "Case based", "Education loan option")],
    "business": [bank("SBI", 11.20, 11.60, 16.50, "As per scheme + GST", "7 yrs", "Case based", "Public sector MSME option"), bank("HDFC Bank", 11.90, 12.25, 21.00, "Up to 2.50% + GST", "4 yrs", "Up to Rs 75 L", "Fast business loan"), bank("ICICI Bank", 12.00, 12.35, 22.00, "Up to 2% + GST", "5 yrs", "Case based", "Private bank working capital"), bank("Axis Bank", 13.00, 13.35, 21.00, "Up to 2% + GST", "5 yrs", "Case based", "Flexible business finance"), bank("Bank of Baroda", 10.85, 11.20, 17.50, "As per scheme + GST", "7 yrs", "Case based", "Competitive MSME pricing"), bank("IDBI Bank", 12.25, 12.60, 18.50, "Up to 1.50% + GST", "5 yrs", "Case based", "Business loan option")],
}

CACHE: Dict[str, Dict[str, Any]] = {}


def bank_rates(loan_type: str = "home", refresh: bool = False) -> dict:
    loan_type = loan_type if loan_type in FALLBACK_RATES else "home"
    now = time.time()
    if not refresh and loan_type in CACHE and CACHE[loan_type]["expires_at"] > now:
        return deepcopy(CACHE[loan_type]["payload"])
    banks = deepcopy(FALLBACK_RATES[loan_type])
    # Simple public-page scrape attempt. Fallback values remain if scraping fails.
    try:
        scrape_public_rates(loan_type, banks)
    except Exception:
        pass
    best = min(bank["salariedMin"] for bank in banks)
    best_set = False
    for item in banks:
        item["isBest"] = False
        if item["salariedMin"] == best and not best_set:
            item["isBest"] = True
            best_set = True
    payload = {"loanType": loan_type, "lastUpdated": ist_now(), "banks": banks}
    CACHE[loan_type] = {"expires_at": now + 6 * 60 * 60, "payload": deepcopy(payload)}
    return payload


def scrape_public_rates(loan_type: str, banks: list) -> None:
    # Kept intentionally defensive: public sites may block bots or change markup.
    url_map = {
        "home": "https://www.paisabazaar.com/home-loan/interest-rates/",
        "personal": "https://www.paisabazaar.com/personal-loan/interest-rates/",
        "car": "https://www.paisabazaar.com/car-loan/interest-rates/",
        "education": "https://www.paisabazaar.com/education-loan/interest-rates/",
        "business": "https://www.paisabazaar.com/business-loan/interest-rates/",
        "lap": "https://www.paisabazaar.com/loan-against-property/",
    }
    response = requests.get(url_map[loan_type], timeout=6, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    lines = [" | ".join(cell.get_text(" ", strip=True) for cell in row.select("th,td")) for row in soup.select("tr")]
    for bank_item in banks:
        for line in lines:
            if bank_item["name"].lower() in line.lower():
                rates = [float(raw) for raw in re.findall(r"(\d{1,2}(?:\.\d{1,2})?)\s*%", line) if 5 <= float(raw) <= 30]
                if rates:
                    delta = bank_item["selfMin"] - bank_item["salariedMin"]
                    bank_item["salariedMin"] = min(rates)
                    bank_item["selfMin"] = round(min(rates) + delta, 2)
                    bank_item["minRate"] = min(rates)
                    bank_item["maxRate"] = max(rates)


def ist_now() -> str:
    ist = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(ist)
    return f"{now.day} {now.strftime('%B %Y, %I:%M %p')}"


def inr(value: float) -> str:
    return f"Rs {round(value):,}"


def compact(value: float) -> str:
    if value >= 10_000_000:
        return f"Rs {value / 10_000_000:.2f} Cr"
    if value >= 100_000:
        return f"Rs {value / 100_000:.2f} L"
    return inr(value)


def type_from_slug(slug: str) -> Optional[str]:
    for key, cfg in LOAN_CONFIGS.items():
        if cfg.slug == slug:
            return key
    return None


@app.route("/")
def index():
    return redirect(url_for("page", slug="home-loan"))


@app.route("/<slug>")
def page(slug: str):
    loan_type = type_from_slug(slug) or "home"
    encoded = request.args.get("state")
    input_data = EligibilityInput(loan_type=loan_type)
    if encoded:
        try:
            input_data = EligibilityInput.from_mapping(json.loads(unquote(base64.urlsafe_b64decode(encoded).decode())))
            input_data.loan_type = loan_type
        except Exception:
            pass
    result = calculate(input_data)
    return render_template_string(TEMPLATE, configs=LOAN_CONFIGS, active=loan_type, initial=asdict(input_data), result=result)


@app.post("/api/calculate")
def api_calculate():
    input_data = EligibilityInput.from_mapping(request.get_json(silent=True) or {})
    return jsonify({"input": asdict(input_data), "result": calculate(input_data)})


@app.get("/api/bank-rates")
def api_bank_rates():
    payload = bank_rates(request.args.get("loanType", "home"), request.args.get("refresh", "").lower() == "true")
    response = jsonify(payload)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


TEMPLATE = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LoanCheck</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = { theme: { extend: { colors: { brand: { blue: "#185FA5", ink: "#102033", mist: "#F5F8FB", line: "#D9E2EC" } } } } };
  </script>
</head>
<body class="bg-white text-brand-ink">
  <header class="border-b border-brand-line bg-brand-mist">
    <div class="mx-auto max-w-7xl px-4 py-6">
      <h1 class="text-4xl font-extrabold">LoanCheck</h1>
      <p class="mt-2 text-slate-600">Python single-file loan eligibility calculator with live lender rate comparison.</p>
      <nav class="mt-4 flex flex-wrap gap-2">
        {% for key, cfg in configs.items() %}
        <a class="rounded-md px-3 py-2 text-sm font-bold {{ 'bg-brand-blue text-white' if key == active else 'bg-white text-slate-700' }}" href="/{{ cfg.slug }}">{{ cfg.label }}</a>
        {% endfor %}
      </nav>
    </div>
  </header>

  <main class="mx-auto grid max-w-7xl gap-6 px-4 py-6 lg:grid-cols-[1fr_420px]">
    <section class="space-y-6">
      <form id="form" class="rounded-lg border border-brand-line bg-white p-5 shadow">
        <input type="hidden" name="loan_type" value="{{ active }}">
        <h2 class="text-2xl font-extrabold">Eligibility inputs</h2>
        <div class="mt-4 grid gap-4 sm:grid-cols-2">
          <label class="text-sm font-bold">Full name<input class="mt-2 w-full rounded border p-2" name="full_name" value="{{ initial.full_name }}"></label>
          <label class="text-sm font-bold">Date of birth<input class="mt-2 w-full rounded border p-2" type="date" name="dob" value="{{ initial.dob }}"></label>
          <label class="text-sm font-bold">Gender<select class="mt-2 w-full rounded border p-2" name="gender"><option value="male">Male</option><option value="female">Female</option><option value="other">Other</option></select></label>
          <label class="text-sm font-bold">Employment<select class="mt-2 w-full rounded border p-2" name="employment_type"><option value="salaried">Salaried</option><option value="self-employed">Self-employed</option><option value="professional">Professional</option><option value="nri">NRI</option><option value="pensioner">Pensioner</option></select></label>
          <label class="text-sm font-bold">Monthly income<input class="mt-2 w-full accent-brand-blue" type="range" min="10000" max="1000000" step="5000" name="monthly_income" value="{{ initial.monthly_income }}"><span data-show="monthly_income"></span></label>
          <label class="text-sm font-bold">Existing EMIs<input class="mt-2 w-full accent-brand-blue" type="range" min="0" max="200000" step="1000" name="existing_emis" value="{{ initial.existing_emis }}"><span data-show="existing_emis"></span></label>
          <label class="text-sm font-bold">CIBIL<input class="mt-2 w-full accent-brand-blue" type="range" min="300" max="900" name="cibil" value="{{ initial.cibil }}"><span data-show="cibil"></span></label>
          <label class="text-sm font-bold">Tenure<input class="mt-2 w-full accent-brand-blue" type="range" min="1" max="30" name="preferred_tenure_years" value="{{ initial.preferred_tenure_years }}"><span data-show="preferred_tenure_years"></span> yrs</label>
          <label class="text-sm font-bold">Property / vehicle value<input class="mt-2 w-full rounded border p-2" type="number" name="property_value" value="{{ initial.property_value }}"></label>
          <label class="flex items-center gap-2 text-sm font-bold"><input type="checkbox" name="has_co_applicant"> Add co-applicant</label>
        </div>
      </form>

      <section class="rounded-lg border border-brand-line bg-white p-5 shadow">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h2 class="text-2xl font-extrabold">Current lender rates</h2>
            <p class="text-sm text-slate-500">Last updated: <span id="updated">Loading...</span></p>
          </div>
          <button id="refresh" class="rounded border px-3 py-2 text-sm font-bold text-brand-blue">Refresh</button>
        </div>
        <div class="mt-4 inline-flex rounded-lg bg-brand-mist p-1">
          <button class="borrower rounded-md bg-brand-blue px-3 py-2 text-sm font-bold text-white" data-type="salaried">Salaried</button>
          <button class="borrower rounded-md px-3 py-2 text-sm font-bold" data-type="self">Self-employed</button>
        </div>
        <div id="rates" class="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3"></div>
        <div id="details" class="mt-4"></div>
        <div id="recommendation" class="mt-4 rounded-lg bg-blue-50 p-4 text-sm"></div>
      </section>
    </section>

    <aside id="result" class="rounded-lg border border-brand-line bg-white p-5 shadow lg:sticky lg:top-4 lg:self-start"></aside>
  </main>

<script>
let state = {{ initial | tojson }};
let result = {{ result | tojson }};
let ratesPayload = null;
let borrower = "salaried";
let selectedBank = "";
const form = document.querySelector("#form");

const money = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const inr = (value) => money.format(Math.max(0, Math.round(value || 0)));
const compact = (value) => value >= 10000000 ? `₹${(value/10000000).toFixed(2)} Cr` : value >= 100000 ? `₹${(value/100000).toFixed(2)} L` : inr(value);

function readForm() {
  const fd = new FormData(form);
  state = Object.fromEntries(fd.entries());
  for (const key of ["monthly_income", "existing_emis", "cibil", "preferred_tenure_years", "property_value"]) state[key] = Number(state[key] || 0);
  state.has_co_applicant = fd.has("has_co_applicant");
}

async function calculate() {
  readForm();
  const response = await fetch("/api/calculate", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(state) });
  const data = await response.json();
  state = data.input;
  result = data.result;
  render();
}

async function loadRates(refresh=false) {
  const response = await fetch(`/api/bank-rates?loanType=${state.loan_type}${refresh ? "&refresh=true" : ""}`);
  ratesPayload = await response.json();
  render();
}

function currentBank() {
  if (!ratesPayload) return null;
  if (selectedBank) return ratesPayload.banks.find((bank) => bank.name === selectedBank);
  return [...ratesPayload.banks].sort((a,b) => displayRate(a) - displayRate(b))[0];
}

function displayRate(bank) {
  return borrower === "self" ? bank.selfMin : bank.salariedMin;
}

function render() {
  document.querySelectorAll("[data-show]").forEach(el => {
    const key = el.dataset.show;
    el.textContent = key.includes("income") || key.includes("emis") ? inr(state[key]) : state[key];
  });
  const marketRate = currentBank() ? displayRate(currentBank()) : result.interest_rate;
  document.querySelector("#result").innerHTML = `
    <p class="text-sm font-bold text-slate-500">Maximum eligible amount</p>
    <p class="mt-1 text-4xl font-extrabold text-brand-blue">${compact(result.max_loan)}</p>
    <div class="mt-5 grid grid-cols-2 gap-3">
      ${metric("Monthly EMI", inr(result.monthly_emi))}
      ${metric("Rate offered", `${marketRate.toFixed(2)}%<span class='block text-xs font-normal text-slate-500'>(based on current market rates)</span>`)}
      ${metric("Total interest", inr(result.total_interest))}
      ${metric("Score", `${result.score}%`)}
    </div>
    <div class="mt-5 rounded-lg bg-brand-mist p-4 font-bold">${result.verdict}</div>`;

  if (!ratesPayload) return;
  document.querySelector("#updated").textContent = ratesPayload.lastUpdated;
  const min = Math.min(...ratesPayload.banks.map(displayRate));
  const max = Math.max(...ratesPayload.banks.map(displayRate));
  document.querySelector("#rates").innerHTML = ratesPayload.banks.map(bank => {
    const rate = displayRate(bank);
    const width = max === min ? 100 : 100 - ((rate - min) / (max - min)) * 72;
    return `<button class="bank rounded-lg border p-4 text-left ${selectedBank === bank.name ? "border-brand-blue bg-blue-50" : ""}" data-bank="${bank.name}">
      <div class="flex justify-between gap-2"><strong>${bank.name}</strong>${bank.isBest ? "<span class='rounded-full bg-emerald-50 px-2 py-1 text-xs text-emerald-700'>Lowest rate</span>" : ""}</div>
      <p class="mt-2 text-3xl font-extrabold text-brand-blue">${rate.toFixed(2)}%</p>
      <p class="text-sm text-slate-600">up to ${bank.maxRate.toFixed(2)}% p.a.</p>
      <div class="mt-3 h-1.5 rounded-full bg-slate-100"><div class="h-full rounded-full bg-brand-blue" style="width:${width}%"></div></div>
    </button>`;
  }).join("");
  document.querySelectorAll(".bank").forEach(btn => btn.onclick = () => { selectedBank = selectedBank === btn.dataset.bank ? "" : btn.dataset.bank; render(); });
  const bank = currentBank();
  document.querySelector("#details").innerHTML = bank ? `<div class="rounded-lg bg-brand-mist p-4"><strong>${bank.name} details</strong><div class="mt-3 grid gap-2 sm:grid-cols-3">${metric("Salaried", bank.salariedMin.toFixed(2)+"%")}${metric("Self-employed", bank.selfMin.toFixed(2)+"%")}${metric("Range", bank.minRate.toFixed(2)+"% - "+bank.maxRate.toFixed(2)+"%")}${metric("Tenure", bank.tenure)}${metric("Max loan", bank.maxLoan)}${metric("Processing", bank.processing)}</div></div>` : "";
  document.querySelector("#recommendation").innerHTML = bank ? `<strong>${bank.name}</strong> looks best right now because it has the lowest displayed starting rate.` : "";
}

function metric(label, value) {
  return `<div class="rounded bg-brand-mist p-3"><p class="text-xs font-bold uppercase text-slate-500">${label}</p><p class="mt-1 font-bold">${value}</p></div>`;
}

form.addEventListener("input", calculate);
document.querySelector("#refresh").onclick = () => loadRates(true);
document.querySelectorAll(".borrower").forEach(btn => btn.onclick = () => {
  borrower = btn.dataset.type;
  document.querySelectorAll(".borrower").forEach(x => x.className = "borrower rounded-md px-3 py-2 text-sm font-bold");
  btn.className = "borrower rounded-md bg-brand-blue px-3 py-2 text-sm font-bold text-white";
  selectedBank = "";
  render();
});
render();
loadRates();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
