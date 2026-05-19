from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from math import ceil
from typing import Optional, Tuple

from .config import LOAN_CONFIGS
from .formatters import clamp


@dataclass
class EligibilityInput:
    full_name: str = ""
    dob: str = "1992-01-01"
    gender: str = "male"
    pan_type: str = "individual"
    employment_type: str = "salaried"
    city: str = "metro"
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
    purpose: str = "purchase"

    @classmethod
    def from_mapping(cls, payload: dict) -> "EligibilityInput":
        data = asdict(cls())
        for key in data:
            if key in payload:
                data[key] = payload[key]
        for key in [
            "monthly_income",
            "other_income",
            "existing_emis",
            "co_applicant_income",
            "property_value",
        ]:
            data[key] = _to_float(data[key])
        for key in ["dependants", "cibil", "co_applicant_cibil", "preferred_tenure_years"]:
            data[key] = int(_to_float(data[key]))
        data["has_co_applicant"] = str(data["has_co_applicant"]).lower() in {"1", "true", "on", "yes"}
        if data["loan_type"] not in LOAN_CONFIGS:
            data["loan_type"] = "home"
        return cls(**data)


@dataclass
class AmortisationYear:
    year: int
    opening_balance: float
    principal: float
    interest: float
    closing_balance: float


def _to_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def calculate_age(dob: str, as_of: Optional[date] = None) -> int:
    as_of = as_of or date.today()
    try:
        birth = datetime.strptime(dob, "%Y-%m-%d").date()
    except ValueError:
        return 0
    age = as_of.year - birth.year
    if (as_of.month, as_of.day) < (birth.month, birth.day):
        age -= 1
    return age


def monthly_emi_per_rupee(annual_rate: float, tenure_years: float) -> float:
    months = max(1, round(tenure_years * 12))
    monthly_rate = annual_rate / 100 / 12
    if monthly_rate == 0:
        return 1 / months
    factor = (1 + monthly_rate) ** months
    return (monthly_rate * factor) / (factor - 1)


def loan_from_emi(emi: float, annual_rate: float, tenure_years: float) -> float:
    return max(0, emi / monthly_emi_per_rupee(annual_rate, tenure_years))


def calculate_balance_transfer_savings(
    outstanding: float,
    current_rate: float,
    new_rate: float,
    remaining_years: int,
    processing_fee: float = 10_000,
) -> dict[str, float]:
    old_emi = outstanding * monthly_emi_per_rupee(current_rate, remaining_years)
    new_emi = outstanding * monthly_emi_per_rupee(new_rate, remaining_years)
    return {
        "old_emi": old_emi,
        "new_emi": new_emi,
        "monthly_saving": old_emi - new_emi,
        "total_saving": (old_emi - new_emi) * remaining_years * 12 - processing_fee,
    }


def calculate_eligibility(input_data: EligibilityInput, as_of: Optional[date] = None) -> dict:
    config = LOAN_CONFIGS[input_data.loan_type]
    age = calculate_age(input_data.dob, as_of)
    retirement_age = 60 if input_data.employment_type in {"salaried", "pensioner"} else 65
    years_to_retirement = retirement_age - age
    age_limited_tenure = max(1, years_to_retirement) if age >= 21 else 1
    max_tenure_years = int(clamp(min(config.max_tenure_years, age_limited_tenure), 1, config.max_tenure_years))
    selected_tenure_years = int(clamp(input_data.preferred_tenure_years, 1, max_tenure_years))
    primary_cibil = int(clamp(input_data.cibil, 300, 900))
    co_cibil = int(clamp(input_data.co_applicant_cibil, 300, 900))
    blended_cibil = round(primary_cibil * 0.7 + co_cibil * 0.3) if input_data.has_co_applicant else primary_cibil

    interest_rate = config.base_rate + _cibil_adjustment(blended_cibil)
    if input_data.gender == "female":
        interest_rate -= 0.05
    if input_data.employment_type == "nri":
        interest_rate += 0.25
    if input_data.employment_type == "professional":
        interest_rate -= 0.10
    if input_data.rate_type == "fixed":
        interest_rate += 0.35
    interest_rate = clamp(interest_rate, config.min_rate, config.max_rate + 3)

    total_income = max(0, input_data.monthly_income + input_data.other_income + (input_data.co_applicant_income if input_data.has_co_applicant else 0))
    adjusted_foir = clamp(config.foir - input_data.dependants * 0.015, 0.25, 0.60)
    available_emi = max(0, total_income * adjusted_foir - input_data.existing_emis)
    emi_per_rupee = monthly_emi_per_rupee(interest_rate, selected_tenure_years)
    foir_based_loan = available_emi / emi_per_rupee
    ltv_based_loan = input_data.property_value * config.ltv if config.ltv else None
    max_loan = max(0, min(foir_based_loan, ltv_based_loan if ltv_based_loan is not None else foir_based_loan))
    monthly_emi = max_loan * emi_per_rupee
    total_payable = monthly_emi * selected_tenure_years * 12
    total_interest = max(0, total_payable - max_loan)
    foir_ratio = (input_data.existing_emis + monthly_emi) / total_income if total_income else 1

    cibil_score = clamp(((blended_cibil - 300) / 600) * 100, 0, 100)
    foir_score = clamp((1 - foir_ratio / 0.65) * 100, 0, 100)
    score = round(clamp(cibil_score * 0.35 + foir_score * 0.35 + _age_score(age) * 0.20 + _income_score(total_income) * 0.10, 0, 100))
    verdict, verdict_tone = _verdict(score)

    warnings = []
    if age < 21:
        warnings.append("Most lenders require the primary applicant to be at least 21 years old.")
    if age > 65:
        warnings.append("Age may restrict tenure significantly; consider adding a younger co-applicant.")
    if input_data.cibil < 300 or input_data.cibil > 900:
        warnings.append("CIBIL should be between 300 and 900; LoanCheck normalised it for this estimate.")
    if primary_cibil < 650:
        warnings.append("CIBIL below 650 can lead to rejection or a much higher rate.")
    if total_income < 25_000:
        warnings.append("Income is low for standard underwriting; eligibility may be limited.")
    if available_emi <= 0:
        warnings.append("Existing EMI obligations consume the current repayment capacity.")

    tips = []
    if blended_cibil < 750:
        better_rate = clamp(config.base_rate + _cibil_adjustment(800), config.min_rate, config.max_rate + 3)
        saving = (monthly_emi_per_rupee(interest_rate, selected_tenure_years) - monthly_emi_per_rupee(better_rate, selected_tenure_years)) * max(max_loan, 1_000_000)
        tips.append(f"Improve CIBIL by {max(1, 750 - blended_cibil)} points to potentially save about ₹{round(max(0, saving)):,}/month on EMI.")
    if foir_ratio > 0.50:
        tips.append("Reduce existing EMIs or choose a longer tenure to improve FOIR comfort.")
    if input_data.dependants >= 3:
        tips.append("Adding a co-applicant can offset dependant load and improve approval strength.")
    if config.secured and ltv_based_loan is not None and ltv_based_loan < foir_based_loan:
        tips.append("The asset value is capping eligibility. A higher down payment or property value changes the limit.")
    if not tips:
        tips.append("Your profile is balanced. Keep credit utilisation low until disbursal.")

    return {
        "age": age,
        "retirement_age": retirement_age,
        "max_tenure_years": max_tenure_years,
        "selected_tenure_years": selected_tenure_years,
        "interest_rate": interest_rate,
        "total_income": total_income,
        "available_emi": available_emi,
        "foir_based_loan": foir_based_loan,
        "ltv_based_loan": ltv_based_loan,
        "max_loan": max_loan,
        "monthly_emi": monthly_emi,
        "total_payable": total_payable,
        "total_interest": total_interest,
        "score": score,
        "verdict": verdict,
        "verdict_tone": verdict_tone,
        "warnings": warnings,
        "tips": tips,
        "foir_ratio": foir_ratio,
        "amortisation": [asdict(row) for row in build_amortisation(max_loan, interest_rate, selected_tenure_years)],
    }


def build_amortisation(principal: float, annual_rate: float, tenure_years: int) -> list[AmortisationYear]:
    months = max(1, round(tenure_years * 12))
    monthly_rate = annual_rate / 100 / 12
    emi = principal * monthly_emi_per_rupee(annual_rate, tenure_years)
    balance = principal
    rows = []
    for year in range(1, ceil(months / 12) + 1):
        opening_balance = balance
        principal_paid = 0.0
        interest_paid = 0.0
        for _ in range(min(12, months - (year - 1) * 12)):
            interest = balance * monthly_rate
            principal_component = min(balance, emi - interest)
            interest_paid += interest
            principal_paid += principal_component
            balance = max(0, balance - principal_component)
        rows.append(AmortisationYear(year, opening_balance, principal_paid, interest_paid, balance))
    return rows


def _cibil_adjustment(cibil: int) -> float:
    if cibil >= 800:
        return -0.25
    if cibil >= 750:
        return 0
    if cibil >= 700:
        return 0.5
    if cibil >= 650:
        return 1
    return 2.5


def _age_score(age: int) -> int:
    if age < 21 or age > 70:
        return 15
    if 25 <= age <= 45:
        return 100
    if age <= 55:
        return 80
    if age <= 62:
        return 55
    return 35


def _income_score(total_income: float) -> int:
    if total_income >= 250_000:
        return 100
    if total_income >= 100_000:
        return 82
    if total_income >= 50_000:
        return 62
    if total_income >= 25_000:
        return 40
    return 20


def _verdict(score: int) -> Tuple[str, str]:
    if score >= 82:
        return "Excellent - Apply Now", "excellent"
    if score >= 68:
        return "Good", "good"
    if score >= 50:
        return "Fair - Improve profile", "fair"
    return "Low - Build credit first", "low"
