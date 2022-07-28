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
from warehouse.organizations.models import Organization, OrganizationSubscription
from warehouse.utils.attrs import make_repr


class SubscriptionStatus(str, enum.Enum):

    Active = "active"
    PastDue = "past_due"
    Unpaid = "unpaid"
    Canceled = "canceled"
    Incomplete = "incomplete"
    IncompleteExpired = "incomplete_expired"
    Trialing = "trialing"

    @classmethod
    def has_value(cls, value):
        return value in set(item.value for item in SubscriptionStatus)


class SubscriptionPriceInterval(str, enum.Enum):

    Month = "month"
    Year = "year"
    Week = "week"
    Day = "day"


class Subscription(db.Model):

    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("subscriptions_customer_id_idx", "customer_id"),
        Index("subscriptions_subscription_id_idx", "subscription_id"),
        UniqueConstraint(
            "customer_id",
            "subscription_id",
            name="_subscription_customer_subscription_uc",
        ),
    )

    __repr__ = make_repr("customer_id", "subscription_id")

    customer_id = Column(
        ForeignKey("organizations.customer_id", onupdate="CASCADE"), nullable=False
    )  # generated by Payment Service Provider

    subscription_id = (
        Column(  # Not to be confused with subscription.id which is our UUID
            Text, nullable=False
        )
    )  # generated by Payment Service Provider
    subscription_price_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription_prices.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(
        Enum(SubscriptionStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    subscription_price = orm.relationship("SubscriptionPrice", lazy=False)
    organization = orm.relationship(
        Organization,
        secondary=OrganizationSubscription.__table__,  # type: ignore
        back_populates="subscriptions",
        uselist=False,
        viewonly=True,
    )

    @property
    def is_restricted(self):
        if self.status != SubscriptionStatus.Active.value:
            return True
        return False


class SubscriptionProduct(db.Model):

    __tablename__ = "subscription_products"

    __repr__ = make_repr("product_name")

    product_id = Column(Text, nullable=True)  # generated by Payment Service Provider
    product_name = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=sql.true())
    tax_code = Column(Text, nullable=True)  # https://stripe.com/docs/tax/tax-categories


class SubscriptionPrice(db.Model):

    __tablename__ = "subscription_prices"

    __repr__ = make_repr("price_id", "product_id", "unit_amount", "recurring")

    price_id = Column(Text, nullable=True)  # generated by Payment Service Provider
    currency = Column(Text, nullable=False)  # https://stripe.com/docs/currencies
    subscription_product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription_products.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    )
    unit_amount = Column(Integer, nullable=False)  # positive integer in cents
    is_active = Column(Boolean, nullable=False, server_default=sql.true())
    recurring = Column(
        Enum(SubscriptionPriceInterval, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    tax_behavior = Column(
        Text, nullable=True
    )  # TODO: Enum? inclusive, exclusive, unspecified

    subscription_product = orm.relationship("SubscriptionProduct", lazy=False)
