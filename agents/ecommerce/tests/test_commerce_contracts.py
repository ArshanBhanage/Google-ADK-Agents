import uuid

import pytest
from agents.ecommerce.models import Action
from pydantic import ValidationError


def test_model_text_cannot_supply_user_identity() -> None:
    with pytest.raises(ValidationError):
        Action.model_validate(
            {
                "action": "create",
                "request_id": str(uuid.uuid4()),
                "confirmed": True,
                "subject": "someone-else",
            }
        )


@pytest.mark.parametrize("confirmation", [False, None, "yes"])
def test_mutations_need_confirmation(confirmation: object) -> None:
    with pytest.raises(ValidationError):
        Action.model_validate(
            {"action": "create", "request_id": str(uuid.uuid4()), "confirmed": confirmation}
        )


@pytest.mark.parametrize("quantity", [-1, 0, 21])
def test_quantity_limits(quantity: int) -> None:
    with pytest.raises(ValidationError):
        Action.model_validate(
            {
                "action": "add",
                "request_id": str(uuid.uuid4()),
                "confirmed": True,
                "cart_id": str(uuid.uuid4()),
                "variant_id": "gid://shopify/ProductVariant/1",
                "quantity": quantity,
            }
        )


def test_checkout_requires_owned_cart_reference() -> None:
    with pytest.raises(ValidationError):
        Action.model_validate(
            {"action": "checkout", "request_id": str(uuid.uuid4()), "confirmed": True}
        )
