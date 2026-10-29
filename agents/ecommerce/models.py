import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Variant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^gid://shopify/ProductVariant/\d+$")
    title: str
    sku: str | None
    amount: Decimal = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    available: bool
    image_url: str | None


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^gid://shopify/Product/\d+$")
    title: str
    description: str
    vendor: str
    product_type: str
    handle: str
    url: str | None
    updated_at: datetime
    variants: list[Variant]


class SyncResult(BaseModel):
    status: str
    products: int
    variants: int
    completed_at: datetime
    database_mode: str


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: uuid.UUID
    action: Literal["create", "add", "remove", "checkout"]
    confirmed: Literal[True]
    cart_id: uuid.UUID | None = None
    variant_id: str | None = Field(default=None, pattern=r"^gid://shopify/ProductVariant/\d+$")
    line_id: str | None = Field(default=None, max_length=512)
    quantity: int = Field(default=1, ge=1, le=20)

    @model_validator(mode="after")
    def required_fields(self) -> "Action":
        if self.action != "create" and self.cart_id is None:
            raise ValueError("cart_id required")
        if self.action == "add" and not self.variant_id:
            raise ValueError("variant_id required")
        if self.action == "remove" and not self.line_id:
            raise ValueError("line_id required")
        return self


class Chat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=2000)
