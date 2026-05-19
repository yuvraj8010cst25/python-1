from __future__ import annotations

import re
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup


CACHE_SECONDS = 6 * 60 * 60

BANK_ALIASES = {
    "SBI": ["sbi", "state bank of india"],
    "HDFC Bank": ["hdfc bank", "hdfc"],
    "ICICI Bank": ["icici bank", "icici"],
    "Axis Bank": ["axis bank", "axis"],
    "Bank of Baroda": ["bank of baroda", "bob"],
    "IDBI Bank": ["idbi bank", "idbi"],
}

PRODUCT_SOURCES = {
    "home": [
        "https://www.paisabazaar.com/home-loan/interest-rates/",
        "https://www.bankbazaar.com/home-loan.html",
    ],
    "lap": [
        "https://www.paisabazaar.com/loan-against-property/",
        "https://www.bankbazaar.com/mortgage-loan.html",
    ],
    "personal": [
        "https://www.paisabazaar.com/personal-loan/interest-rates/",
        "https://www.bankbazaar.com/personal-loan.html",
    ],
    "car": [
        "https://www.paisabazaar.com/car-loan/interest-rates/",
        "https://www.bankbazaar.com/car-loan.html",
    ],
    "education": [
        "https://www.paisabazaar.com/education-loan/interest-rates/",
        "https://www.bankbazaar.com/education-loan.html",
    ],
    "business": [
        "https://www.paisabazaar.com/business-loan/interest-rates/",
        "https://www.bankbazaar.com/business-loan.html",
    ],
}

PRODUCT_LABELS = {
    "home": "home loan",
    "lap": "loan against property",
    "personal": "personal loan",
    "car": "car loan",
    "education": "education loan",
    "business": "business loan",
}


def _bank(
    name: str,
    salaried_min: float,
    self_min: float,
    max_rate: float,
    processing: str,
    tenure: str,
    max_loan: str,
    tag: str,
) -> Dict[str, Any]:
    return {
        "name": name,
        "salariedMin": salaried_min,
        "selfMin": self_min,
        "minRate": min(salaried_min, self_min),
        "maxRate": max_rate,
        "processing": processing,
        "tenure": tenure,
        "maxLoan": max_loan,
        "tag": tag,
        "isBest": False,
    }


FALLBACK_RATES: Dict[str, List[Dict[str, Any]]] = {
    "home": [
        _bank("SBI", 7.50, 7.65, 8.45, "0.35% + GST", "30 yrs", "No limit", "Strong public sector option"),
        _bank("HDFC Bank", 7.90, 8.00, 9.15, "Up to 0.50% + GST", "30 yrs", "Case based", "Large private lender"),
        _bank("ICICI Bank", 7.70, 7.85, 9.00, "Up to 0.50% + GST", "30 yrs", "Case based", "Fast private bank processing"),
        _bank("Axis Bank", 8.35, 8.50, 9.15, "Up to 1% + GST", "30 yrs", "Up to Rs 5 Cr", "Flexible loan variants"),
        _bank("Bank of Baroda", 7.20, 7.35, 9.25, "0.35% + GST", "30 yrs", "No limit", "Lowest public sector rate"),
        _bank("IDBI Bank", 8.50, 8.65, 9.65, "0.50% + GST", "30 yrs", "Case based", "Simple salaried profile option"),
    ],
    "lap": [
        _bank("SBI", 9.75, 9.90, 11.30, "1% + GST", "15 yrs", "Case based", "Stable public sector LAP"),
        _bank("HDFC Bank", 9.50, 9.75, 11.50, "Up to 1% + GST", "15 yrs", "Case based", "Competitive LAP pricing"),
        _bank("ICICI Bank", 9.60, 9.85, 11.75, "Up to 1% + GST", "15 yrs", "Case based", "Fast private bank processing"),
        _bank("Axis Bank", 10.50, 10.75, 12.40, "Up to 1% + GST", "20 yrs", "Case based", "Longer LAP tenure"),
        _bank("Bank of Baroda", 9.15, 9.35, 11.25, "0.50% + GST", "15 yrs", "Case based", "Public sector LAP value"),
        _bank("IDBI Bank", 10.00, 10.25, 12.00, "1% + GST", "15 yrs", "Case based", "Simple property-backed loan"),
    ],
    "personal": [
        _bank("SBI", 11.45, 11.70, 15.30, "Up to 1.50% + GST", "6 yrs", "Up to Rs 20 L", "Lower PSU personal loan rate"),
        _bank("HDFC Bank", 10.85, 11.10, 24.00, "Up to Rs 6,500 + GST", "6 yrs", "Up to Rs 40 L", "Fast digital disbursal"),
        _bank("ICICI Bank", 10.80, 11.05, 16.15, "Up to 2% + GST", "6 yrs", "Up to Rs 50 L", "Competitive private bank option"),
        _bank("Axis Bank", 10.99, 11.25, 22.00, "Up to 2% + GST", "7 yrs", "Up to Rs 40 L", "Flexible tenure"),
        _bank("Bank of Baroda", 10.90, 11.20, 18.25, "Up to 2% + GST", "7 yrs", "Up to Rs 20 L", "Public sector personal loan"),
        _bank("IDBI Bank", 11.00, 11.30, 15.50, "1% + GST", "5 yrs", "Up to Rs 5 L", "Straightforward offer"),
    ],
    "car": [
        _bank("SBI", 8.75, 8.90, 9.80, "0.25% + GST", "7 yrs", "Up to 90% on-road", "Strong car loan rate"),
        _bank("HDFC Bank", 8.90, 9.10, 11.00, "Up to 1% + GST", "7 yrs", "Up to 100% ex-showroom", "Fast private bank option"),
        _bank("ICICI Bank", 8.85, 9.05, 10.75, "Up to 1% + GST", "7 yrs", "Up to 100% ex-showroom", "Competitive car loan"),
        _bank("Axis Bank", 9.10, 9.30, 12.00, "Up to 1% + GST", "7 yrs", "Up to 100% on-road", "Flexible car finance"),
        _bank("Bank of Baroda", 8.70, 8.90, 10.25, "0.50% + GST", "7 yrs", "Up to 90% on-road", "Lowest car loan start"),
        _bank("IDBI Bank", 9.00, 9.25, 10.50, "0.50% + GST", "7 yrs", "Up to 90% on-road", "Simple car loan option"),
    ],
    "education": [
        _bank("SBI", 8.05, 8.20, 11.15, "As per scheme", "15 yrs", "Case based", "Popular education loan"),
        _bank("HDFC Bank", 9.50, 9.75, 13.50, "Up to 1% + GST", "15 yrs", "Case based", "Private education finance"),
        _bank("ICICI Bank", 9.85, 10.10, 13.75, "Up to 1% + GST", "10 yrs", "Case based", "Study loan option"),
        _bank("Axis Bank", 10.50, 10.75, 15.00, "Up to 2% + GST", "15 yrs", "Case based", "Higher-ticket education loans"),
        _bank("Bank of Baroda", 8.15, 8.35, 12.00, "As per scheme", "15 yrs", "Case based", "Public sector education loan"),
        _bank("IDBI Bank", 9.20, 9.45, 12.75, "As per scheme", "15 yrs", "Case based", "Education loan option"),
    ],
    "business": [
        _bank("SBI", 11.20, 11.60, 16.50, "As per scheme + GST", "7 yrs", "Case based", "Public sector MSME option"),
        _bank("HDFC Bank", 11.90, 12.25, 21.00, "Up to 2.50% + GST", "4 yrs", "Up to Rs 75 L", "Fast business loan"),
        _bank("ICICI Bank", 12.00, 12.35, 22.00, "Up to 2% + GST", "5 yrs", "Case based", "Private bank working capital"),
        _bank("Axis Bank", 13.00, 13.35, 21.00, "Up to 2% + GST", "5 yrs", "Case based", "Flexible business finance"),
        _bank("Bank of Baroda", 10.85, 11.20, 17.50, "As per scheme + GST", "7 yrs", "Case based", "Competitive MSME pricing"),
        _bank("IDBI Bank", 12.25, 12.60, 18.50, "Up to 1.50% + GST", "5 yrs", "Case based", "Business loan option"),
    ],
}

_CACHE: Dict[str, Dict[str, Any]] = {}


def get_bank_rates(loan_type: str = "home", force_refresh: bool = False) -> Dict[str, Any]:
    loan_type = loan_type if loan_type in FALLBACK_RATES else "home"
    now = time.time()
    cached = _CACHE.get(loan_type)
    if not force_refresh and cached and cached["expires_at"] > now:
        return deepcopy(cached["payload"])

    banks = _fresh_bank_rates(loan_type)
    payload = {
        "loanType": loan_type,
        "productLabel": PRODUCT_LABELS[loan_type],
        "lastUpdated": _format_ist_now(),
        "banks": _mark_best_bank(banks),
    }
    _CACHE[loan_type] = {"expires_at": now + CACHE_SECONDS, "payload": deepcopy(payload)}
    return payload


def _fresh_bank_rates(loan_type: str) -> List[Dict[str, Any]]:
    banks = deepcopy(FALLBACK_RATES[loan_type])
    try:
        page_text = _fetch_source_text(loan_type)
        if page_text:
            scraped = _extract_rates(page_text)
            for bank in banks:
                match = scraped.get(bank["name"])
                if match:
                    self_delta = bank["selfMin"] - bank["salariedMin"]
                    bank["minRate"] = match["minRate"]
                    bank["maxRate"] = max(match["maxRate"], match["minRate"])
                    bank["salariedMin"] = match["minRate"]
                    bank["selfMin"] = round(match["minRate"] + self_delta, 2)
    except Exception:
        return banks
    return banks


def _fetch_source_text(loan_type: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
        )
    }
    chunks = []
    for url in PRODUCT_SOURCES[loan_type]:
        try:
            response = requests.get(url, headers=headers, timeout=8)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            chunks.extend(_table_like_text(soup))
        except Exception:
            continue
    return "\n".join(chunks)


def _table_like_text(soup: BeautifulSoup) -> List[str]:
    rows: List[str] = []
    for row in soup.select("tr"):
        text = " | ".join(cell.get_text(" ", strip=True) for cell in row.select("th,td"))
        if text:
            rows.append(text)
    for item in soup.select("li, p"):
        text = item.get_text(" ", strip=True)
        if "%" in text:
            rows.append(text)
    return rows


def _extract_rates(source_text: str) -> Dict[str, Dict[str, float]]:
    scraped: Dict[str, Dict[str, float]] = {}
    for line in source_text.splitlines():
        clean = re.sub(r"\s+", " ", line.strip())
        lower = clean.lower()
        if "%" not in clean:
            continue
        rates = _rates_from_text(clean)
        if not rates:
            continue
        for bank_name, aliases in BANK_ALIASES.items():
            if bank_name in scraped:
                continue
            if any(alias in lower for alias in aliases):
                scraped[bank_name] = {
                    "minRate": min(rates),
                    "maxRate": max(rates) if len(rates) > 1 else min(rates),
                }
    return scraped


def _rates_from_text(text: str) -> List[float]:
    rates = []
    for raw in re.findall(r"(?<!\d)(\d{1,2}(?:\.\d{1,2})?)\s*%", text):
        value = float(raw)
        if 5 <= value <= 30:
            rates.append(value)
    return rates


def _mark_best_bank(banks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best_rate = min(bank["salariedMin"] for bank in banks)
    best_applied = False
    for bank in banks:
        bank["isBest"] = False
        if not best_applied and bank["salariedMin"] == best_rate:
            bank["isBest"] = True
            best_applied = True
    return banks


def _format_ist_now() -> str:
    ist = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(ist)
    return f"{now.day} {now.strftime('%B %Y, %I:%M %p')}"
