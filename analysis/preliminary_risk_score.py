import math


THRESHOLDS = {
    "inflation": 10.0,
    "real_wage": -5.0,
    "currency_3m": 10.0,
    "reserves_3m": -20.0,
}


def valid_number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def percentage_change(current, previous):
    current = valid_number(current)
    previous = valid_number(previous)

    if current is None or previous is None or previous <= 0:
        return None

    return (current / previous - 1.0) * 100.0


def calculate_risk(
    inflation=None,
    wage_growth=None,
    usd_lkr=None,
    usd_lkr_3m_ago=None,
    reserves=None,
    reserves_3m_ago=None,
):
    inflation = valid_number(inflation)
    wage_growth = valid_number(wage_growth)

    real_wage_growth = None

    if (
        inflation is not None
        and wage_growth is not None
        and inflation > -100
        and wage_growth > -100
    ):
        real_wage_growth = (
            (1 + wage_growth / 100)
            / (1 + inflation / 100)
            - 1
        ) * 100

    currency_change = percentage_change(
        usd_lkr, usd_lkr_3m_ago
    )

    reserve_change = percentage_change(
        reserves, reserves_3m_ago
    )

    signals = [
        {
            "indicator": "Inflation Pressure",
            "value": inflation,
            "threshold": "Inflation >= 10%",
            "triggered": (
                inflation >= THRESHOLDS["inflation"]
                if inflation is not None else None
            ),
        },
        {
            "indicator": "Real Wage Pressure",
            "value": real_wage_growth,
            "threshold": "Real wage growth <= -5%",
            "triggered": (
                real_wage_growth <= THRESHOLDS["real_wage"]
                if real_wage_growth is not None else None
            ),
        },
        {
            "indicator": "Currency Pressure",
            "value": currency_change,
            "threshold": "3-month USD/LKR increase >= 10%",
            "triggered": (
                currency_change >= THRESHOLDS["currency_3m"]
                if currency_change is not None else None
            ),
        },
        {
            "indicator": "Reserve Pressure",
            "value": reserve_change,
            "threshold": "3-month reserves decline >= 20%",
            "triggered": (
                reserve_change <= THRESHOLDS["reserves_3m"]
                if reserve_change is not None else None
            ),
        },
    ]

    available = sum(
        s["triggered"] is not None for s in signals
    )

    triggered = sum(
        s["triggered"] is True for s in signals
    )

    # Do not publish an overall score when
    # fewer than three indicators are available.
    score = (
        round(100 * triggered / available, 1)
        if available >= 3 else None
    )

    return {
        "signals": signals,
        "score": score,
        "available": available,
        "total": len(signals),
        "triggered": triggered,
        "real_wage_growth": real_wage_growth,
        "currency_change_3m": currency_change,
        "reserve_change_3m": reserve_change,
    }


def run_tests():
    # All inputs missing -> no score
    empty = calculate_risk()
    assert empty["score"] is None
    assert empty["available"] == 0

    # Exactly three signals, all three triggered.
    result = calculate_risk(
        inflation=12,
        wage_growth=3,
        usd_lkr=330,
        usd_lkr_3m_ago=300
    )
    assert result["available"] == 3
    assert result["triggered"] == 3
    assert result["score"] == 100.0

    # Only two available indicators -> insufficient coverage.
    partial = calculate_risk(
        inflation=12,
        usd_lkr=330,
        usd_lkr_3m_ago=300
    )
    assert partial["score"] is None

    print("All preliminary risk-scoring tests passed.")


if __name__ == "__main__":
    run_tests()
