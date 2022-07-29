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

# import datetime

import stripe

from sqlalchemy import or_
from sqlalchemy.orm.exc import NoResultFound
from zope.interface import implementer

from warehouse.organizations.models import Organization, OrganizationSubscription
from warehouse.subscriptions.interfaces import IBillingService, ISubscriptionService
from warehouse.subscriptions.models import (
    Subscription,
    SubscriptionPrice,
    SubscriptionPriceInterval,
    SubscriptionProduct,
    SubscriptionStatus,
)

# from dateutil import relativedelta


class GenericBillingService:
    def __init__(self, api, publishable_key, webhook_secret):
        self.api = api
        self.publishable_key = publishable_key
        self.webhook_secret = webhook_secret

    @classmethod
    def create_service(cls, context, request):
        """
        Create appropriate billing service based on environment
        """
        raise NotImplementedError

    def get_checkout_session(self, session_id):
        """
        Fetch the Checkout Session to based on the session_id passed to the success page
        """
        checkout_session = self.api.checkout.Session.retrieve(
            session_id,
            expand=["customer", "line_items", "subscription"],
        )
        return checkout_session

    def get_customer(self, subscription_id):
        """
        Fetch the Customer resource attached to the Subscription
        """
        subscription = self.api.Subscription.retrieve(
            subscription_id,
            expand=["customer"],
        )
        return subscription.customer

    def create_customer(self, name, description):
        """
        Create the Customer resource via Billing API with the given name and description
        """
        return self.api.Customer.create(
            name=name,
            description=description,
        )

    def create_checkout_session(self, customer_id, price_id, success_url, cancel_url):
        """
        # Create new Checkout Session for the order
        # For full details see https://stripe.com/docs/api/checkout/sessions/create
        """
        checkout_session = self.api.checkout.Session.create(
            customer=customer_id,
            # TODO: What payment methods will we accept?
            # payment_method_types=['card'],
            success_url=success_url + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            mode="subscription",
            # automatic_tax={'enabled': True},
            line_items=[{"price": price_id, "quantity": 1}],
            # # TODO: Will these work with stripe checkout?
            # billing_cycle_anchor=first_day_next_month,
            # proration_behavior="none",
        )
        return checkout_session

    def create_portal_session(self, customer_id, return_url):
        """
        Return customer portal session to allow customer to managing their subscription
        """
        portal_session = self.api.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return portal_session

    # See Stripe webhook documentation:
    # https://stripe.com/docs/api/webhook_endpoints/create#create_webhook_endpoint-enabled_events
    # https://stripe.com/docs/webhooks/quickstart
    def webhook_received(self, payload, sig_header):
        """
        Return parsed webhook event from Stripe
        """
        return stripe.Webhook.construct_event(payload, sig_header, self.webhook_secret)

    def create_or_update_product(self, name, description, tax_code):
        """
        Create product resource via Billing API, or update an active
        product resource with the same name
        """
        product_search = self.search_products(f'active:"true" name:"{name}"')
        products = product_search["data"]
        if products:
            product = max(products, key=lambda p: p["created"])
            return self.update_product(product["id"], name, description, tax_code)
        else:
            return self.create_product(name, description, tax_code)

    def create_product(self, name, description, tax_code):
        """
        Create and return a product resource via Billing API
        """
        return self.api.Product.create(
            name=name, description=description, tax_code=tax_code
        )

    def retrieve_product(self, product_id):
        """
        Get a product resource by id via Billing API
        """
        return self.api.Product.retrieve(product_id)

    def update_product(self, product_id, name, description, tax_code):
        """
        Update a product resource via Billing API
        only allowing update of those attributes we use
        return the updated product
        """
        return self.api.Product.modify(
            product_id,
            name=name,
            description=description,
            tax_code=tax_code,
        )

    def list_all_products(self, limit=10):
        """
        Get list of all price resources via Billing API
        Limit can range between 1 and 100, default is 10
        """
        return self.api.Product.list(limit=limit)

    def delete_product(self, product_id):
        """
        Delete a product resource via Billing API
        """
        return self.api.Product.delete(product_id)

    def search_products(self, query, limit=10):
        """
        Search for product resources via Billing API
        example: query="active:'true'"
        """
        return self.api.Product.search(query=query, limit=limit)

    def sync_product(self, subscription_product):
        """
        Synchronize a product resource via Billing API with a
        subscription product from the database.
        """
        product = self.create_or_update_product(
            name=subscription_product.product_name,
            description=subscription_product.description,
            tax_code=subscription_product.tax_code,
            # See Stripe docs for tax codes. https://stripe.com/docs/tax/tax-categories
        )
        subscription_product.product_id = product["id"]

    def create_or_update_price(
        self, unit_amount, currency, recurring, product_id, tax_behavior
    ):
        """
        Create price resource via Billing API, or update an active price
        resource with the same product and currency
        """
        # Deactivate existing prices.
        price_search = self.search_prices(
            f'active:"true" product:"{product_id}" currency:"{currency}"'
        )
        prices = price_search["data"]
        for price in prices:
            self.update_price(price["id"], active=False)
        # Create new price.
        return self.create_price(
            unit_amount,
            currency,
            recurring,
            product_id,
            tax_behavior,
        )

    def create_price(self, unit_amount, currency, recurring, product_id, tax_behavior):
        """
        Create and return a price resource via Billing API
        """
        # TODO: Hard-coding to a month for recurring interval
        #       as that is the requirement at this time
        return self.api.Price.create(
            unit_amount=unit_amount,
            currency=currency,
            recurring={"interval": "month"},  # {"interval": recurring},
            product=product_id,
            tax_behavior=tax_behavior,
        )

    def retrieve_price(self, price_id):
        """
        Get a price resource via Billing API
        """
        return self.api.Price.retrieve(price_id)

    def update_price(self, price_id, active):
        """
        Update a price resource by id via Billing API
        only allowing update of those attributes we use
        return the updated price
        """
        return self.api.Price.modify(
            price_id,
            active=active,
        )

    def list_all_prices(self, limit=10):
        """
        Get list of all price resources via Billing API
        Limit can range between 1 and 100, default is 10
        """
        return self.api.Price.list(limit=limit)

    def search_prices(self, query, limit=10):
        """
        Search for price resources via Billing API
        example: query="active:'true'"
        """
        return self.api.Price.search(query=query, limit=limit)

    def sync_price(self, subscription_price):
        """
        Synchronize a price resource via Billing API with a
        subscription price from the database.
        """
        price = self.create_or_update_price(
            unit_amount=subscription_price.unit_amount,
            currency=subscription_price.currency,
            recurring=subscription_price.recurring.value,
            product_id=subscription_price.subscription_product.product_id,
            tax_behavior=subscription_price.tax_behavior,
        )
        subscription_price.price_id = price["id"]


@implementer(IBillingService)
class LocalBillingService(GenericBillingService):
    @classmethod
    def create_service(cls, context, request):
        # Override api_base to hit mock-stripe in development
        stripe.api_base = request.registry.settings["subscription.api_base"]
        stripe.api_version = request.registry.settings["subscription.api_version"]
        stripe.api_key = request.registry.settings["subscription.secret_key"]
        publishable_key = request.registry.settings["subscription.publishable_key"]
        webhook_secret = request.registry.settings["subscription.webhook_key"]

        return cls(stripe, publishable_key, webhook_secret)


@implementer(IBillingService)
class StripeBillingService(GenericBillingService):
    @classmethod
    def create_service(cls, context, request):
        stripe.api_version = request.registry.settings["subscription.api_version"]
        stripe.api_key = request.registry.settings["subscription.secret_key"]
        publishable_key = request.registry.settings["subscription.publishable_key"]
        webhook_secret = request.registry.settings["subscription.webhook_key"]

        return cls(stripe, publishable_key, webhook_secret)


@implementer(ISubscriptionService)
class SubscriptionService:
    def __init__(self, db_session):
        self.db = db_session

    def get_subscription(self, id):
        """
        Get a subscription by id
        """
        return self.db.query(Subscription).get(id)

    def find_subscriptionid(self, subscription_id):
        """
        Find the unique subscription identifier for the subscription,
        by the payment service provider subscription id or None
        """
        try:
            (id,) = (
                self.db.query(Subscription.id)
                .filter(
                    Subscription.subscription_id == subscription_id,
                )
                .one()
            )
        except NoResultFound:
            return

        return id

    def add_subscription(self, customer_id, subscription_id):
        """
        Attempts to create a subscription object for the organization
        with the specified customer ID and subscription ID
        """
        # Get default subscription price.
        subscription_price = self.get_or_create_default_subscription_price()

        # Add new subscription.
        subscription = Subscription(
            customer_id=customer_id,
            subscription_id=subscription_id,
            subscription_price_id=subscription_price.id,
            status=SubscriptionStatus.Active,  # default active subscription
        )

        # Link to organization.
        organization = (
            self.db.query(Organization)
            .filter(Organization.customer_id == customer_id)
            .one()
        )
        organization_subscription = OrganizationSubscription(
            organization=organization,
            subscription=subscription,
        )

        self.db.add(subscription)
        self.db.add(organization_subscription)
        self.db.flush()  # get back the subscription id

        return subscription

    def update_subscription_status(self, id, status):
        """
        Update the status of a subscription object by subscription.id
        """
        self.db.query(Subscription).filter(
            Subscription.id == id,
        ).update({Subscription.status: status})

    def delete_subscription(self, id):
        """
        Delete a subscription by ID
        """
        subscription = self.get_subscription(id)

        # Delete link to organization
        self.db.query(OrganizationSubscription).filter_by(
            subscription=subscription
        ).delete()

        self.db.delete(subscription)
        self.db.flush()

    def get_subscriptions_by_customer(self, customer_id):
        """
        Get a list of subscriptions tied to the given customer ID
        """
        return (
            self.db.query(Subscription)
            .filter(Subscription.customer_id == customer_id)
            .all()
        )

    def delete_customer(self, customer_id):
        """
        Deletes a customer and all associated subscription data
        """
        subscriptions = self.get_subscriptions_by_customer(customer_id)

        for subscription in subscriptions:
            self.delete_subscription(subscription.id)

        # Null the customer field in the organization object
        self.db.query(Organization).filter(
            Organization.customer_id == customer_id
        ).update({Organization.customer_id: None})

    def get_subscription_product(self, subscription_product_id):
        """
        Get a product by subscription product id
        """
        return self.db.query(SubscriptionProduct).get(subscription_product_id)

    def get_subscription_products(self):
        """
        Get a list of all products
        """
        return (
            self.db.query(SubscriptionProduct)
            .order_by(SubscriptionProduct.product_name)
            .all()
        )

    def find_subscription_productid(self, search_term):
        """
        Find the unique product identifier for the product name,
        product id or None if nothing is found
        """
        try:
            (subscription_product_id,) = (
                self.db.query(SubscriptionProduct.id)
                .filter(
                    or_(
                        SubscriptionProduct.product_name == search_term,
                        SubscriptionProduct.product_id == search_term,
                    )
                )
                .one()
            )
        except NoResultFound:
            return

        return subscription_product_id

    def add_subscription_product(self, product_name, description, product_id, tax_code):
        """
        Add a subscription product
        """
        subscription_product = SubscriptionProduct(
            product_name=product_name,
            description=description,
            product_id=product_id,
            tax_code=tax_code,
        )

        self.db.add(subscription_product)
        self.db.flush()

        return subscription_product

    def update_subscription_product(self, subscription_product_id, **changes):
        """
        Accepts a subscription product object
        and attempts an update with those attributes
        """
        subscription_product = self.get_subscription_product(subscription_product_id)
        for attr, value in changes.items():
            setattr(subscription_product, attr, value)

        return subscription_product

    def delete_subscription_product(self, subscription_product_id):
        """
        Delete a subscription product
        """
        subscription_product = self.get_subscription_product(subscription_product_id)

        self.db.delete(subscription_product)
        self.db.flush()

    def get_or_create_default_subscription_price(self):
        """
        Get the default subscription price or initialize one if nothing is found
        """
        try:
            subscription_price = (
                self.db.query(SubscriptionPrice)
                .filter(SubscriptionPrice.is_active)
                .one()
            )
        except NoResultFound:
            subscription_product = self.add_subscription_product(
                product_name="PyPI",
                description="Organization account for companies",
                product_id=None,
                tax_code="txcd_10103001"  # "Software as a service (SaaS) - business use" # noqa: E501
                # See Stripe docs for tax codes. https://stripe.com/docs/tax/tax-categories # noqa: E501
            )
            subscription_price = self.add_subscription_price(
                price_id=None,
                currency="usd",
                subscription_product_id=subscription_product.id,
                unit_amount=5000,
                recurring=SubscriptionPriceInterval.Month,
                tax_behavior="inclusive",
            )

        return subscription_price

    def get_subscription_price(self, subscription_price_id):
        """
        Get a subscription price by id
        """
        return self.db.query(SubscriptionPrice).get(subscription_price_id)

    def get_subscription_prices(self):
        """
        Get a list of all subscription prices
        """
        return self.db.query(SubscriptionPrice).order_by(SubscriptionPrice.id).all()

    def find_subscription_priceid(self, search_term):
        """
        Find the unique price identifier for the price id,
        subscription product id or None if nothing is found
        """
        try:
            (subscription_price_id,) = (
                self.db.query(SubscriptionPrice.id)
                .filter(
                    SubscriptionPrice.price_id == search_term,
                )
                .one()
            )
        except NoResultFound:
            return

        return subscription_price_id

    def add_subscription_price(
        self,
        price_id,
        currency,
        subscription_product_id,
        unit_amount,
        recurring,
        tax_behavior,
    ):
        """
        Add a subscription price
        """
        subscription_price = SubscriptionPrice(
            price_id=price_id,
            currency=currency,
            subscription_product_id=subscription_product_id,
            unit_amount=unit_amount,
            recurring=recurring,
            tax_behavior=tax_behavior,
        )

        self.db.add(subscription_price)
        self.db.flush()

        return subscription_price

    def update_subscription_price(self, subscription_price_id, **changes):
        """
        Accepts a subscription price object
        and attempts an update with those attributes
        """
        subscription_price = self.get_subscription_price(subscription_price_id)
        for attr, value in changes.items():
            setattr(subscription_price, attr, value)

        return subscription_price

    def delete_subscription_price(self, subscription_price_id):
        """
        Delete a subscription price
        """
        subscription_price = self.get_subscription_price(subscription_price_id)

        self.db.delete(subscription_price)
        self.db.flush()


def subscription_factory(context, request):
    return SubscriptionService(request.db)
