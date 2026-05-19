from loancheck.app import create_app
from loancheck.bank_rates import get_bank_rates


def test_bank_rates_payload_has_six_banks_and_one_best_for_each_product():
    for loan_type in ["home", "lap", "personal", "car", "education", "business"]:
        payload = get_bank_rates(loan_type=loan_type, force_refresh=True)

        assert payload["loanType"] == loan_type
        assert "lastUpdated" in payload
        assert len(payload["banks"]) == 6
        assert sum(1 for bank in payload["banks"] if bank["isBest"]) == 1


def test_bank_rates_endpoint_sets_cors_header(monkeypatch):
    app = create_app()

    with app.test_client() as client:
        response = client.get("/api/bank-rates?loanType=personal")

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    payload = response.get_json()
    assert payload["loanType"] == "personal"
    assert len(payload["banks"]) == 6
