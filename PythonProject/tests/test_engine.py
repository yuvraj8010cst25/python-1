from datetime import date

from loancheck.engine import (
    EligibilityInput,
    calculate_balance_transfer_savings,
    calculate_eligibility,
    loan_from_emi,
)


def test_secured_loan_is_capped_by_ltv():
    result = calculate_eligibility(
        EligibilityInput(
            loan_type="home",
            monthly_income=1_000_000,
            existing_emis=0,
            property_value=5_000_000,
        )
    )

    assert result["max_loan"] <= 4_000_000


def test_weak_cibil_has_higher_rate_than_strong_cibil():
    weak = calculate_eligibility(EligibilityInput(cibil=620))
    strong = calculate_eligibility(EligibilityInput(cibil=820))

    assert weak["interest_rate"] > strong["interest_rate"]


def test_tenure_is_limited_by_retirement_age():
    result = calculate_eligibility(
        EligibilityInput(
            dob="1970-01-01",
            employment_type="salaried",
            preferred_tenure_years=30,
        ),
        as_of=date(2026, 5, 18),
    )

    assert result["selected_tenure_years"] <= 4


def test_balance_transfer_savings_are_positive_when_rate_drops():
    result = calculate_balance_transfer_savings(2_500_000, 11, 9.5, 10, 10_000)

    assert result["monthly_saving"] > 0
    assert result["total_saving"] > 0


def test_affordability_reverse_calculates_amount():
    amount = loan_from_emi(50_000, 9, 20)

    assert amount > 5_000_000
