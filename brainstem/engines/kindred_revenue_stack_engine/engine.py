from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RevenueStackPlan:
    product_name: str
    offer_statement: str
    price_model: dict[str, Any]
    payment_path: list[str]
    payout_path: list[str]
    allocation_model: dict[str, float]
    gross_margin_review: str
    recommended_next_action: str


class KindredRevenueStackEngine:
    """
    Kindred Revenue Stack Engine, KRSE.

    Native BRAINSTEM engine for turning approved products into clear USD pathways:
    offer, pricing, payment path, margin, payout, reserve, reinvestment, and spendable USD logic.

    This v1 does not process real payments.
    It generates revenue readiness plans.
    """

    DEFAULT_ALLOCATION = {
        "reserve_taxes_and_buffer_percent": 30.0,
        "operations_tools_compute_percent": 20.0,
        "reinvestment_marketing_percent": 20.0,
        "personal_pay_percent": 30.0,
    }

    DEFAULT_PAYMENT_PATH = [
        "Customer sees offer",
        "Customer pays through payment page",
        "Payment processor balance receives funds",
        "Funds become available for payout",
        "Payout reaches connected bank account",
        "Money becomes spendable USD",
    ]

    def generate_plan(self, candidate: dict[str, Any]) -> RevenueStackPlan:
        product_name = candidate.get("name", "Unnamed Product")
        buyer = candidate.get("target_buyer", "target buyer")
        deliverable = candidate.get("deliverable", "deliverable")
        price_model = candidate.get("price_model", {"type": "unknown", "amount_usd": None})

        amount = price_model.get("amount_usd")
        price_text = f"" if amount is not None else "a defined price"

        offer_statement = (
            f"{product_name} helps {buyer} receive {deliverable} for {price_text}."
        )

        estimated_margin = candidate.get("estimated_gross_margin_percent", 0)
        compute_cost = candidate.get("estimated_compute_cost_monthly_usd", 0)

        if estimated_margin >= 70 and compute_cost <= 25:
            margin_review = "Strong early margin profile if delivery remains controlled."
            next_action = "Prepare payment page, intake path, and delivery workflow."
        elif estimated_margin >= 50:
            margin_review = "Acceptable margin profile, but delivery and compute cost need monitoring."
            next_action = "Refine pricing, scope, or compute model before scaling."
        else:
            margin_review = "Weak margin profile. Pricing, scope, or compute cost must be improved."
            next_action = "Send candidate to Refinery Loop before revenue launch."

        return RevenueStackPlan(
            product_name=product_name,
            offer_statement=offer_statement,
            price_model=price_model,
            payment_path=self.DEFAULT_PAYMENT_PATH,
            payout_path=[
                "Payment processor",
                "Available balance",
                "Connected bank account",
                "Spendable USD",
            ],
            allocation_model=self.DEFAULT_ALLOCATION,
            gross_margin_review=margin_review,
            recommended_next_action=next_action,
        )
