from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


LoanType = str


@dataclass(frozen=True)
class LoanConfig:
    type: LoanType
    slug: str
    label: str
    hindi_label: str
    icon: str
    min_rate: float
    max_rate: float
    base_rate: float
    max_tenure_years: int
    foir: float
    secured: bool
    ltv: Optional[float]
    meta_description: str


LOAN_CONFIGS: dict[LoanType, LoanConfig] = {
    "home": LoanConfig(
        type="home",
        slug="home-loan",
        label="Home Loan",
        hindi_label="होम लोन",
        icon="home",
        min_rate=8.5,
        max_rate=10,
        base_rate=9,
        max_tenure_years=30,
        foir=0.50,
        secured=True,
        ltv=0.80,
        meta_description="Estimate home loan eligibility in India with LTV, FOIR, EMI and amortisation.",
    ),
    "lap": LoanConfig(
        type="lap",
        slug="lap",
        label="Loan Against Property",
        hindi_label="संपत्ति पर लोन",
        icon="building",
        min_rate=9.5,
        max_rate=11,
        base_rate=10.25,
        max_tenure_years=20,
        foir=0.50,
        secured=True,
        ltv=0.65,
        meta_description="Calculate loan against property eligibility with India-specific LTV and FOIR rules.",
    ),
    "personal": LoanConfig(
        type="personal",
        slug="personal-loan",
        label="Personal Loan",
        hindi_label="पर्सनल लोन",
        icon="landmark",
        min_rate=11,
        max_rate=24,
        base_rate=14,
        max_tenure_years=5,
        foir=0.45,
        secured=False,
        ltv=None,
        meta_description="Check personal loan eligibility, EMI and interest rate based on income and CIBIL.",
    ),
    "car": LoanConfig(
        type="car",
        slug="car-loan",
        label="Car Loan",
        hindi_label="कार लोन",
        icon="car",
        min_rate=9,
        max_rate=12,
        base_rate=10,
        max_tenure_years=7,
        foir=0.48,
        secured=True,
        ltv=0.85,
        meta_description="Estimate car loan eligibility in India with LTV, EMI, tenure and credit score factors.",
    ),
    "education": LoanConfig(
        type="education",
        slug="education-loan",
        label="Education Loan",
        hindi_label="एजुकेशन लोन",
        icon="graduation-cap",
        min_rate=10.5,
        max_rate=13,
        base_rate=11.25,
        max_tenure_years=15,
        foir=0.45,
        secured=False,
        ltv=None,
        meta_description="Calculate education loan eligibility, EMI and repayment structure for Indian borrowers.",
    ),
    "business": LoanConfig(
        type="business",
        slug="business-loan",
        label="Business Loan",
        hindi_label="बिजनेस लोन",
        icon="briefcase-business",
        min_rate=12,
        max_rate=18,
        base_rate=14.5,
        max_tenure_years=10,
        foir=0.55,
        secured=False,
        ltv=None,
        meta_description="Check business loan eligibility with FOIR, income, credit score and EMI calculations.",
    ),
}


FAQS: dict[LoanType, list[dict[str, str]]] = {
    "home": [
        {"q": "What is the maximum LTV for a home loan?", "a": "LoanCheck uses up to 80% LTV for home loans, subject to income and credit profile."},
        {"q": "Can my tenure go up to 30 years?", "a": "Yes, but the effective tenure is reduced if retirement age falls before the selected horizon."},
        {"q": "Does a co-applicant improve eligibility?", "a": "Usually yes. Their income is added and their CIBIL is blended into the profile score."},
        {"q": "Is floating or fixed rate better?", "a": "Floating can move with market rates; fixed gives payment certainty and is modelled slightly higher here."},
        {"q": "Can I use this for construction?", "a": "Yes, choose Construction as the purpose to estimate eligibility for build-related borrowing."},
    ],
    "lap": [
        {"q": "How is LAP eligibility different?", "a": "LAP is secured by property, but LoanCheck caps LTV at 65% and uses a shorter maximum tenure."},
        {"q": "Can business owners apply for LAP?", "a": "Yes, self-employed and professional profiles are supported in the calculator."},
        {"q": "Does property value decide the final amount?", "a": "It creates the LTV cap; the final result is the lower of LTV-based and FOIR-based eligibility."},
        {"q": "Is LAP rate higher than home loan?", "a": "Typically yes. LoanCheck models LAP rates from 9.5% to 11% before profile adjustments."},
        {"q": "Can LAP be used for top-up?", "a": "Yes, select Top-up as the loan purpose to model that scenario."},
    ],
    "personal": [
        {"q": "Is collateral needed for a personal loan?", "a": "No. The calculator uses income, existing EMI, CIBIL and profile inputs without LTV."},
        {"q": "Why is the rate range wider?", "a": "Unsecured loans price risk more sharply, so LoanCheck models 11% to 24%."},
        {"q": "What CIBIL score is preferred?", "a": "750 and above is generally strong, while scores under 650 materially reduce the result."},
        {"q": "Can pensioners apply?", "a": "Yes, but age and available tenure may lower eligibility."},
        {"q": "Does city category matter?", "a": "It lightly influences the overall profile and affordability assumptions."},
    ],
    "car": [
        {"q": "What LTV is used for car loans?", "a": "LoanCheck applies up to 85% of vehicle value for car loan eligibility."},
        {"q": "Can the tenure be 7 years?", "a": "Yes, if age and employment profile support that repayment horizon."},
        {"q": "Does CIBIL affect car loan rate?", "a": "Yes. Strong credit lowers the rate, while lower credit scores increase it."},
        {"q": "Is down payment considered?", "a": "It is implied by the gap between vehicle value and the LTV-capped loan amount."},
        {"q": "Can I compare 5-year and 7-year tenures?", "a": "Use compare mode to see side-by-side EMI and total interest differences."},
    ],
    "education": [
        {"q": "Is LTV required for education loans?", "a": "No. LoanCheck calculates education loan eligibility mainly from repayment capacity."},
        {"q": "What maximum tenure is used?", "a": "The model allows up to 15 years for education loans."},
        {"q": "Can a co-applicant be included?", "a": "Yes, a co-applicant income and CIBIL can be added in Step 2."},
        {"q": "Does course type affect the estimate?", "a": "This version focuses on borrower profile; lenders may also evaluate course and institution."},
        {"q": "Can I estimate affordability?", "a": "Yes, the affordability tab reverses EMI capacity into an estimated loan amount."},
    ],
    "business": [
        {"q": "Is this for unsecured business loans?", "a": "Yes, this model has no LTV and uses FOIR-led repayment capacity."},
        {"q": "Why is FOIR higher for business loans?", "a": "Business profiles can support higher repayment ratios when income is strong and stable."},
        {"q": "Do professionals get a concession?", "a": "Yes, professional profiles receive a small rate concession in the engine."},
        {"q": "Can companies use this calculator?", "a": "Company PAN is supported, though final lender underwriting may require business financials."},
        {"q": "Can I model balance transfer?", "a": "Yes, use the balance transfer tab to estimate savings after switching lender."},
    ],
}
