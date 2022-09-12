# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import enum

from sqlalchemy import (
    Boolean,
    Column,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    orm,
    sql,
)
from sqlalchemy.dialects.postgresql import UUID

from warehouse import db
from warehouse.i18n import localize as _
from warehouse.organizations.models import Organization, OrganizationStripeSubscription
from warehouse.utils.attrs import make_repr
from warehouse.utils.enum import StrLabelEnum


class StripeSubscriptionStatus(StrLabelEnum):
    # Name = "value", _("Label")
    Active = "active", _("Active")
    PastDue = "past_due", _("Past Due")
    Unpaid = "unpaid", _("Unpaid")
    Canceled = "canceled", _("Canceled")
    Incomplete = "incomplete", _("Incomplete")
    IncompleteExpired = "incomplete_expired", _("Incomplete Expired")
    Trialing = "trialing", _("Trialing")

    @classmethod
    def has_value(cls, value):
        return value in set(item.value for item in StripeSubscriptionStatus)


class StripeSubscriptionPriceInterval(str, enum.Enum):

    Month = "month"
    Year = "year"
    Week = "week"
    Day = "day"


class StripeCustomer(db.Model):

    __tablename__ = "stripe_customers"

    __repr__ = make_repr("customer_id", "billing_email")

    customer_id = Column(
        Text, nullable=False, unique=True
    )  # generated by Payment Service Provider
    billing_email = Column(Text)

    organization = orm.relationship(
        Organization,
        secondary=OrganizationStripeCustomer.__table__,  # type: ignore
        back_populates="customer",
        uselist=False,
        viewonly=True,
    )
    subscriptions = orm.relationship("StripeSubscription", lazy=False)


class StripeSubscription(db.Model):

    __tablename__ = "stripe_subscriptions"
    __table_args__ = (
        Index("stripe_subscriptions_stripe_customer_id_idx", "stripe_customer_id"),
        Index("stripe_subscriptions_subscription_id_idx", "subscription_id"),
        UniqueConstraint(
            "stripe_customer_id",
            "subscription_id",
            name="_stripe_subscription_customer_subscription_uc",
        ),
    )

    __repr__ = make_repr("subscription_id", "stripe_customer_id")

    stripe_customer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("stripe_customers.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    subscription_id = Column(
        Text, nullable=False
    )  # generated by Payment Service Provider
    subscription_price_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "stripe_subscription_prices.id", onupdate="CASCADE", ondelete="CASCADE"
        ),
        nullable=False,
    )
    status = Column(
        Enum(StripeSubscriptionStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    subscription_price = orm.relationship("StripeSubscriptionPrice", lazy=False)
    subscription_item = orm.relationship(
        "StripeSubscriptionItem",
        back_populates="subscription",
        lazy=False,
        uselist=False,
    )
    organization = orm.relationship(
        Organization,
        secondary=OrganizationStripeSubscription.__table__,  # type: ignore
        back_populates="subscriptions",
        uselist=False,
        viewonly=True,
    )
    customer = orm.relationship(
        "StripeCustomer",
        back_populates="subscriptions",
        lazy=False,
        uselist=False,
    )

    @property
    def is_restricted(self):
        return (
            self.status != StripeSubscriptionStatus.Active.value
            and self.status != StripeSubscriptionStatus.Trialing.value
        )


class StripeSubscriptionProduct(db.Model):

    __tablename__ = "stripe_subscription_products"

    __repr__ = make_repr("product_name")

    product_id = Column(Text, nullable=True)  # generated by Payment Service Provider
    product_name = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=sql.true())
    tax_code = Column(Text, nullable=True)  # https://stripe.com/docs/tax/tax-categories


class StripeSubscriptionPrice(db.Model):

    __tablename__ = "stripe_subscription_prices"

    __repr__ = make_repr("price_id", "unit_amount", "recurring")

    price_id = Column(Text, nullable=True)  # generated by Payment Service Provider
    currency = Column(Text, nullable=False)  # https://stripe.com/docs/currencies
    subscription_product_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "stripe_subscription_products.id", onupdate="CASCADE", ondelete="CASCADE"
        ),
        nullable=False,
    )
    unit_amount = Column(Integer, nullable=False)  # positive integer in cents
    is_active = Column(Boolean, nullable=False, server_default=sql.true())
    recurring = Column(
        Enum(
            StripeSubscriptionPriceInterval,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    tax_behavior = Column(
        Text, nullable=True
    )  # TODO: Enum? inclusive, exclusive, unspecified

    subscription_product = orm.relationship("StripeSubscriptionProduct", lazy=False)


class StripeSubscriptionItem(db.Model):

    __tablename__ = "stripe_subscription_items"

    __repr__ = make_repr(
        "subscription_item_id", "subscription_id", "subscription_price_id", "quantity"
    )

    subscription_item_id = Column(
        Text, nullable=True
    )  # generated by Payment Service Provider
    subscription_id = Column(
        UUID(as_uuid=True),
        ForeignKey("stripe_subscriptions.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    subscription_price_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "stripe_subscription_prices.id", onupdate="CASCADE", ondelete="CASCADE"
        ),
        nullable=False,
    )
    quantity = Column(Integer, nullable=False)  # positive integer or zero

    subscription = orm.relationship(
        "StripeSubscription", lazy=False, back_populates="subscription_item"
    )
    subscription_price = orm.relationship("StripeSubscriptionPrice", lazy=False)
