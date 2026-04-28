from __future__ import annotations

from typing import Dict

HIGH_RISK_MERCHANTS = {"crypto", "gift_cards"}
ELEVATED_RISK_MERCHANTS = {"travel"}


def score_transaction(tx: Dict) -> int:
    """Return a simple fraud risk score from 0 to 100."""
    score = 0

    # Device intelligence signal
    if tx["device_risk_score"] >= 70:
        score += 25
    elif tx["device_risk_score"] >= 40:
        score += 10

    # International transaction
    if tx["is_international"] == 1:
        score += 15

    # Purchase amount
    if tx["amount_usd"] >= 1000:
        score += 25
    elif tx["amount_usd"] >= 500:
        score += 10

    # Transaction velocity in the past 24 hours
    if tx["velocity_24h"] >= 6:
        score += 20
    elif tx["velocity_24h"] >= 3:
        score += 5

    # Prior login failures signal potential account takeover
    if tx["failed_logins_24h"] >= 5:
        score += 20
    elif tx["failed_logins_24h"] >= 2:
        score += 10

    # Prior chargeback history
    if tx["prior_chargebacks"] >= 2:
        score += 20
    elif tx["prior_chargebacks"] == 1:
        score += 5

    # KYC level: unverified accounts carry higher identity risk
    if tx.get("kyc_level") == "basic":
        score += 10

    # Account age: new accounts are a primary fraud vector
    account_age = tx.get("account_age_days")
    if account_age is not None:
        if account_age < 30:
            score += 15
        elif account_age < 90:
            score += 8

    # Merchant category: irreversible or easily liquidated categories
    merchant = tx.get("merchant_category", "")
    if merchant in HIGH_RISK_MERCHANTS:
        score += 15
    elif merchant in ELEVATED_RISK_MERCHANTS:
        score += 5

    # Compound penalty: international origin combined with high velocity is a
    # strong account-takeover signal that exceeds the sum of each factor alone
    if tx["is_international"] == 1 and tx["velocity_24h"] >= 6:
        score += 10

    return max(0, min(score, 100))


def label_risk(score: int) -> str:
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"
