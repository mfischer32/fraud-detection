"""
Scenario tests validating the four bug fixes and three planned enhancements.

Run with: pytest tests/test_scoring_improvements.py -v

STATUS LEGEND (per class docstring):
  FAILING NOW  - will fail against current code; pass once the fix is applied
  PASSING NOW  - already correct in current code
  ENHANCEMENT  - will fail until new signals are added to score_transaction()

Groups:
  1. TestBugFixes         - directional regression tests for each inverted sign
  2. TestExactScores      - pinned point values per factor after bug fixes
  3. TestEnhancements     - new signals: KYC level, account age, merchant category, compounding
  4. TestRealTransactions - field values taken directly from transactions.csv / accounts.csv
  5. Parametrized sweep   - all four bugs in one table
"""
from __future__ import annotations

import pytest

from risk_rules import label_risk, score_transaction

# ---------------------------------------------------------------------------
# Shared baselines
# ---------------------------------------------------------------------------

# Perfectly clean transaction - no risk factor should fire
CLEAN_TX = {
    "device_risk_score": 10,
    "is_international": 0,
    "amount_usd": 50,
    "velocity_24h": 1,
    "failed_logins_24h": 0,
    "prior_chargebacks": 0,
}

# Clean transaction extended with the three planned new fields
CLEAN_TX_ENHANCED = {
    **CLEAN_TX,
    "kyc_level": "full",
    "account_age_days": 365,
    "merchant_category": "grocery",
}


# ===========================================================================
# GROUP 1: Bug regression tests
# STATUS: FAILING NOW — each test will pass once the four inverted signs are
# corrected in risk_rules.score_transaction().
# ===========================================================================

class TestBugFixes:
    """
    Each test isolates one inverted-sign bug.

    The assertion is intentionally simple: the risky value of the field must
    produce a *higher* score than the clean value, all else equal.
    """

    def test_high_device_risk_increases_score(self):
        # Bug 1: device_risk_score >= 70 currently subtracts 25 — should add 25.
        low_device = {**CLEAN_TX, "device_risk_score": 10}
        high_device = {**CLEAN_TX, "device_risk_score": 75}
        assert score_transaction(high_device) > score_transaction(low_device), (
            "A device risk score >= 70 should raise fraud risk, not lower it."
        )

    def test_international_increases_score(self):
        # Bug 2: is_international=1 currently subtracts 15 — should add 15.
        domestic = {**CLEAN_TX, "is_international": 0}
        international = {**CLEAN_TX, "is_international": 1}
        assert score_transaction(international) > score_transaction(domestic), (
            "An international transaction should raise fraud risk."
        )

    def test_high_velocity_increases_score(self):
        # Bug 3: velocity_24h >= 6 currently subtracts 20 — should add 20.
        low_velocity = {**CLEAN_TX, "velocity_24h": 1}
        high_velocity = {**CLEAN_TX, "velocity_24h": 8}
        assert score_transaction(high_velocity) > score_transaction(low_velocity), (
            "Six or more transactions in 24 h should raise fraud risk."
        )

    def test_one_prior_chargeback_increases_score(self):
        # Bug 4a: prior_chargebacks == 1 currently subtracts 5 — should add 5.
        no_cb = {**CLEAN_TX, "prior_chargebacks": 0}
        one_cb = {**CLEAN_TX, "prior_chargebacks": 1}
        assert score_transaction(one_cb) > score_transaction(no_cb), (
            "One prior chargeback should raise fraud risk, not lower it."
        )

    def test_two_prior_chargebacks_increases_score(self):
        # Bug 4b: prior_chargebacks >= 2 currently subtracts 20 — should add 20.
        no_cb = {**CLEAN_TX, "prior_chargebacks": 0}
        two_cb = {**CLEAN_TX, "prior_chargebacks": 2}
        assert score_transaction(two_cb) > score_transaction(no_cb), (
            "A repeat chargeback account should score higher than a clean account."
        )

    def test_chargeback_history_is_monotone(self):
        # More chargebacks → higher score, in strict order.
        s0 = score_transaction({**CLEAN_TX, "prior_chargebacks": 0})
        s1 = score_transaction({**CLEAN_TX, "prior_chargebacks": 1})
        s2 = score_transaction({**CLEAN_TX, "prior_chargebacks": 2})
        assert s0 < s1 < s2, (
            f"Scores should rise with chargeback count: 0→{s0}, 1→{s1}, 2→{s2}"
        )

    def test_velocity_is_monotone(self):
        # Higher velocity → higher score, in strict order across both tiers.
        s_low = score_transaction({**CLEAN_TX, "velocity_24h": 1})
        s_mid = score_transaction({**CLEAN_TX, "velocity_24h": 4})
        s_high = score_transaction({**CLEAN_TX, "velocity_24h": 8})
        assert s_low < s_mid < s_high, (
            f"Velocity scores should be monotone: 1→{s_low}, 4→{s_mid}, 8→{s_high}"
        )


# ===========================================================================
# GROUP 2: Exact score pin tests
# STATUS: FAILING NOW — correct once bugs are fixed.
#
# Tests the expected point contribution of each factor in isolation,
# computed against CLEAN_TX so only one factor fires at a time.
# ===========================================================================

class TestExactScores:
    """Pinned point values for each factor. All assume the four bugs are fixed."""

    def test_clean_transaction_scores_zero(self):
        assert score_transaction(CLEAN_TX) == 0

    def test_high_device_risk_adds_25(self):
        # device_risk_score >= 70 → +25
        assert score_transaction({**CLEAN_TX, "device_risk_score": 75}) == 25

    def test_medium_device_risk_adds_10(self):
        # device_risk_score 40–69 → +10
        assert score_transaction({**CLEAN_TX, "device_risk_score": 50}) == 10

    def test_low_device_risk_adds_nothing(self):
        # device_risk_score < 40 → 0
        assert score_transaction({**CLEAN_TX, "device_risk_score": 20}) == 0

    def test_international_adds_15(self):
        assert score_transaction({**CLEAN_TX, "is_international": 1}) == 15

    def test_large_amount_adds_25(self):
        # amount_usd >= 1000 → +25
        assert score_transaction({**CLEAN_TX, "amount_usd": 1500}) == 25

    def test_medium_amount_adds_10(self):
        # amount_usd 500–999 → +10
        assert score_transaction({**CLEAN_TX, "amount_usd": 750}) == 10

    def test_small_amount_adds_nothing(self):
        assert score_transaction({**CLEAN_TX, "amount_usd": 200}) == 0

    def test_high_velocity_adds_20(self):
        # velocity_24h >= 6 → +20
        assert score_transaction({**CLEAN_TX, "velocity_24h": 8}) == 20

    def test_medium_velocity_adds_5(self):
        # velocity_24h 3–5 → +5
        assert score_transaction({**CLEAN_TX, "velocity_24h": 4}) == 5

    def test_high_failed_logins_adds_20(self):
        # failed_logins_24h >= 5 → +20
        assert score_transaction({**CLEAN_TX, "failed_logins_24h": 6}) == 20

    def test_medium_failed_logins_adds_10(self):
        # failed_logins_24h 2–4 → +10
        assert score_transaction({**CLEAN_TX, "failed_logins_24h": 3}) == 10

    def test_two_chargebacks_adds_20(self):
        assert score_transaction({**CLEAN_TX, "prior_chargebacks": 2}) == 20

    def test_one_chargeback_adds_5(self):
        assert score_transaction({**CLEAN_TX, "prior_chargebacks": 1}) == 5

    def test_worst_case_clamped_to_100(self):
        # All max-tier signals: 25+15+25+20+20+20 = 125 → clamped to 100
        worst = {
            "device_risk_score": 85,    # +25
            "is_international": 1,      # +15
            "amount_usd": 2400,         # +25
            "velocity_24h": 10,         # +20
            "failed_logins_24h": 8,     # +20
            "prior_chargebacks": 3,     # +20
        }
        assert score_transaction(worst) == 100

    def test_all_medium_tiers_sum_correctly(self):
        # Medium tier across every factor: 10+10+5+10 = 35 → medium label
        mid = {
            "device_risk_score": 50,    # +10
            "is_international": 0,
            "amount_usd": 750,          # +10
            "velocity_24h": 4,          # +5
            "failed_logins_24h": 3,     # +10
            "prior_chargebacks": 0,
        }
        assert score_transaction(mid) == 35
        assert label_risk(35) == "medium"


# ===========================================================================
# GROUP 3: Enhancement scenario tests
# STATUS: ENHANCEMENT — will FAIL until score_transaction() is updated to
# consume three new fields: kyc_level, account_age_days, merchant_category.
#
# These tests define the *expected* behavior of each planned enhancement.
# They serve as the acceptance criteria for the implementation work.
# ===========================================================================

class TestEnhancements:
    """
    Planned new signals. Pass CLEAN_TX_ENHANCED (includes the new fields) so
    that once score_transaction reads them, these tests immediately turn green.
    """

    # --- KYC level -----------------------------------------------------------

    def test_basic_kyc_increases_score(self):
        full_kyc = {**CLEAN_TX_ENHANCED, "kyc_level": "full"}
        basic_kyc = {**CLEAN_TX_ENHANCED, "kyc_level": "basic"}
        assert score_transaction(basic_kyc) > score_transaction(full_kyc), (
            "Unverified (basic KYC) accounts carry higher fraud risk."
        )

    # --- Account age ---------------------------------------------------------

    def test_brand_new_account_increases_score(self):
        # < 30 days old: highest risk tier for account age
        established = {**CLEAN_TX_ENHANCED, "account_age_days": 365}
        brand_new = {**CLEAN_TX_ENHANCED, "account_age_days": 10}
        assert score_transaction(brand_new) > score_transaction(established), (
            "Accounts under 30 days old are a primary fraud vector."
        )

    def test_young_account_increases_score(self):
        # 30–89 days: elevated but lower than brand new
        established = {**CLEAN_TX_ENHANCED, "account_age_days": 365}
        young = {**CLEAN_TX_ENHANCED, "account_age_days": 60}
        assert score_transaction(young) > score_transaction(established)

    def test_account_age_is_monotone(self):
        # Younger → higher risk, strict ordering across three tiers
        old = score_transaction({**CLEAN_TX_ENHANCED, "account_age_days": 365})
        mid = score_transaction({**CLEAN_TX_ENHANCED, "account_age_days": 60})
        new = score_transaction({**CLEAN_TX_ENHANCED, "account_age_days": 10})
        assert old < mid < new, (
            f"Risk should decrease with account age: 10d→{new}, 60d→{mid}, 365d→{old}"
        )

    # --- Merchant category ---------------------------------------------------

    def test_crypto_merchant_increases_score(self):
        # Crypto purchases are irreversible and a top fraud category
        grocery = {**CLEAN_TX_ENHANCED, "merchant_category": "grocery"}
        crypto = {**CLEAN_TX_ENHANCED, "merchant_category": "crypto"}
        assert score_transaction(crypto) > score_transaction(grocery), (
            "Crypto is irreversible and overrepresented in fraud losses."
        )

    def test_gift_cards_merchant_increases_score(self):
        # Gift cards are easily liquidated — high fraud conversion
        grocery = {**CLEAN_TX_ENHANCED, "merchant_category": "grocery"}
        gift_cards = {**CLEAN_TX_ENHANCED, "merchant_category": "gift_cards"}
        assert score_transaction(gift_cards) > score_transaction(grocery), (
            "Gift cards are easily converted to cash by fraudsters."
        )

    def test_travel_merchant_increases_score(self):
        grocery = {**CLEAN_TX_ENHANCED, "merchant_category": "grocery"}
        travel = {**CLEAN_TX_ENHANCED, "merchant_category": "travel"}
        assert score_transaction(travel) > score_transaction(grocery)

    def test_crypto_scores_higher_than_travel(self):
        # Crypto is harder to claw back than travel bookings
        travel = score_transaction({**CLEAN_TX_ENHANCED, "merchant_category": "travel"})
        crypto = score_transaction({**CLEAN_TX_ENHANCED, "merchant_category": "crypto"})
        assert crypto > travel

    # --- Compound penalty: international + high velocity ---------------------

    def test_international_high_velocity_compounds(self):
        """
        The combination of international origin AND rapid velocity should add
        more than either signal alone (account takeover shipped abroad).
        """
        base = score_transaction(CLEAN_TX_ENHANCED)
        intl_only = score_transaction({**CLEAN_TX_ENHANCED, "is_international": 1, "velocity_24h": 1})
        vel_only = score_transaction({**CLEAN_TX_ENHANCED, "is_international": 0, "velocity_24h": 8})
        both = score_transaction({**CLEAN_TX_ENHANCED, "is_international": 1, "velocity_24h": 8})

        additive_sum = (intl_only - base) + (vel_only - base)
        assert (both - base) > additive_sum, (
            f"Combined effect ({both - base}) should exceed additive sum ({additive_sum})."
        )


# ===========================================================================
# GROUP 4: Real transaction scenarios
# Field values are taken directly from transactions.csv and accounts.csv.
#
# 4a: Confirmed-chargeback transactions — should all score >= medium after fixes.
# 4b: Clean transactions — should score low (or at most medium for large amounts).
# ===========================================================================

class TestRealTransactions:
    """
    STATUS: FAILING NOW for 4a (bugs cause fraud to score low).
    STATUS: PASSING NOW for most of 4b (clean transactions already score low).
    """

    # --- 4a: Confirmed chargebacks -------------------------------------------
    # All eight should reach at least "medium" after the bug fixes.
    # Seven should reach "high"; tx 50008 hits "medium" (lower-tier signals).

    def test_tx_50003_is_high_risk(self):
        # Mia Chen, basic KYC, device=81, intl (PH), $1250 gift_cards, vel=6, logins=5, cb=0
        # Expected score after fixes: 25+15+25+20+20+0 = 105 → 100
        tx = {
            "device_risk_score": 81,
            "is_international": 1,
            "amount_usd": 1250.0,
            "velocity_24h": 6,
            "failed_logins_24h": 5,
            "prior_chargebacks": 0,
        }
        score = score_transaction(tx)
        assert label_risk(score) == "high", f"tx 50003 (confirmed chargeback) scored {score}"

    def test_tx_50006_is_high_risk(self):
        # Ethan Brown, basic KYC, 12d old, device=77, intl (NG), $400, vel=7, logins=6, cb=3
        # Expected score after fixes: 25+15+0+20+20+20 = 100
        tx = {
            "device_risk_score": 77,
            "is_international": 1,
            "amount_usd": 399.99,
            "velocity_24h": 7,
            "failed_logins_24h": 6,
            "prior_chargebacks": 3,
        }
        score = score_transaction(tx)
        assert label_risk(score) == "high", f"tx 50006 (confirmed chargeback) scored {score}"

    def test_tx_50008_is_at_least_medium_risk(self):
        # Mason Wilson, basic KYC, 31d old, device=68, intl (IN), $620, vel=5, logins=3, cb=0
        # Expected score after fixes: 10+15+10+5+10+0 = 50 → medium
        # This is the hardest chargeback to catch — signals are mid-tier only.
        tx = {
            "device_risk_score": 68,
            "is_international": 1,
            "amount_usd": 620.0,
            "velocity_24h": 5,
            "failed_logins_24h": 3,
            "prior_chargebacks": 0,
        }
        score = score_transaction(tx)
        assert label_risk(score) in ("medium", "high"), (
            f"tx 50008 (confirmed chargeback) scored {score} — expected at least medium"
        )

    def test_tx_50011_is_high_risk(self):
        # Harper Allen, basic KYC, 18d old, device=85, intl (RU), $1400 crypto, vel=8, logins=7, cb=1
        # Expected score after fixes: 25+15+25+20+20+5 = 110 → 100
        tx = {
            "device_risk_score": 85,
            "is_international": 1,
            "amount_usd": 1400.0,
            "velocity_24h": 8,
            "failed_logins_24h": 7,
            "prior_chargebacks": 1,
        }
        score = score_transaction(tx)
        assert score == 100, f"tx 50011 should be clamped to 100, got {score}"
        assert label_risk(score) == "high"

    def test_tx_50013_is_high_risk(self):
        # Mia Chen second transaction: device=79, intl (PH), $150, vel=7, logins=5, cb=0
        # Expected score after fixes: 25+15+0+20+20+0 = 80
        tx = {
            "device_risk_score": 79,
            "is_international": 1,
            "amount_usd": 150.0,
            "velocity_24h": 7,
            "failed_logins_24h": 5,
            "prior_chargebacks": 0,
        }
        score = score_transaction(tx)
        assert label_risk(score) == "high", f"tx 50013 (confirmed chargeback) scored {score}"

    def test_tx_50014_is_high_risk(self):
        # Ethan Brown second transaction: device=72, intl (NG), $50, vel=9, logins=7, cb=3
        # Expected score after fixes: 25+15+0+20+20+20 = 100
        tx = {
            "device_risk_score": 72,
            "is_international": 1,
            "amount_usd": 49.99,
            "velocity_24h": 9,
            "failed_logins_24h": 7,
            "prior_chargebacks": 3,
        }
        score = score_transaction(tx)
        assert score == 100, f"tx 50014 should be clamped to 100, got {score}"

    def test_tx_50015_is_high_risk(self):
        # Mason Wilson second transaction: device=71, intl (IN), $910, vel=6, logins=4, cb=0
        # Expected score after fixes: 25+15+10+20+10+0 = 80
        tx = {
            "device_risk_score": 71,
            "is_international": 1,
            "amount_usd": 910.0,
            "velocity_24h": 6,
            "failed_logins_24h": 4,
            "prior_chargebacks": 0,
        }
        score = score_transaction(tx)
        assert label_risk(score) == "high", f"tx 50015 (confirmed chargeback) scored {score}"

    def test_tx_50019_is_high_risk(self):
        # Harper Allen second transaction: device=83, intl (RU), $75, vel=10, logins=8, cb=1
        # Expected score after fixes: 25+15+0+20+20+5 = 85
        tx = {
            "device_risk_score": 83,
            "is_international": 1,
            "amount_usd": 75.0,
            "velocity_24h": 10,
            "failed_logins_24h": 8,
            "prior_chargebacks": 1,
        }
        score = score_transaction(tx)
        assert label_risk(score) == "high", f"tx 50019 (confirmed chargeback) scored {score}"

    # --- 4b: Clean transactions -----------------------------------------------

    def test_tx_50001_is_low_risk(self):
        # Ava Patel, full KYC, device=8, domestic, $45, vel=1, logins=0, cb=0
        # Expected score: 0
        tx = {
            "device_risk_score": 8,
            "is_international": 0,
            "amount_usd": 45.20,
            "velocity_24h": 1,
            "failed_logins_24h": 0,
            "prior_chargebacks": 0,
        }
        score = score_transaction(tx)
        assert label_risk(score) == "low", f"tx 50001 (clean) scored {score}"

    def test_tx_50005_acceptable_false_positive(self):
        # Sophia Garcia VIP, full KYC, device=52, domestic, $2200 travel, vel=1, logins=0, cb=0
        # Expected score after fixes: 10+25 = 35 → medium
        # This is an acceptable false positive — large amount with medium device risk.
        # Enhancements (account age 900d, full KYC) should eventually reduce it to low.
        tx = {
            "device_risk_score": 52,
            "is_international": 0,
            "amount_usd": 2200.0,
            "velocity_24h": 1,
            "failed_logins_24h": 0,
            "prior_chargebacks": 0,
        }
        score = score_transaction(tx)
        assert score <= 40, (
            f"tx 50005 (clean VIP large purchase) scored {score} — "
            "should be low or borderline medium at most"
        )

    def test_tx_50016_is_low_risk(self):
        # Liam Johnson, full KYC, device=9, domestic, $35 grocery, vel=1, logins=0, cb=1
        # Expected score after fixes: 0+5 = 5 → low
        tx = {
            "device_risk_score": 9,
            "is_international": 0,
            "amount_usd": 35.0,
            "velocity_24h": 1,
            "failed_logins_24h": 0,
            "prior_chargebacks": 1,
        }
        score = score_transaction(tx)
        assert label_risk(score) == "low", (
            f"tx 50016 (clean, small amount) scored {score}"
        )


# ===========================================================================
# GROUP 5: Parametrized sweep
# STATUS: FAILING NOW — one row per bug; all four pass once fixes are applied.
# ===========================================================================

@pytest.mark.parametrize("field,risky_val,description", [
    ("device_risk_score", 75,  "high device risk score (>= 70)"),
    ("is_international",   1,  "international transaction"),
    ("velocity_24h",       8,  "high velocity (>= 6 in 24h)"),
    ("prior_chargebacks",  2,  "repeat chargeback account (>= 2)"),
])
def test_each_risk_factor_raises_score(field, risky_val, description):
    """
    Every primary risk signal should produce a higher score than the clean
    baseline when all other factors are held constant.
    """
    clean_score = score_transaction(CLEAN_TX)
    risky_score = score_transaction({**CLEAN_TX, field: risky_val})
    assert risky_score > clean_score, (
        f"{description}: risky score ({risky_score}) should exceed "
        f"clean score ({clean_score})"
    )
