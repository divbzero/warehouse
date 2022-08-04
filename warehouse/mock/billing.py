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


import random

from string import ascii_letters, digits

from pyramid.httpexceptions import HTTPNotFound, HTTPSeeOther
from pyramid.view import view_config, view_defaults

from warehouse.admin.flags import AdminFlagValue
from warehouse.api.billing import handle_billing_webhook_event
from warehouse.organizations.models import Organization
from warehouse.subscriptions.interfaces import IBillingService
from warehouse.subscriptions.services import MockStripeBillingService


@view_defaults(
    context=Organization,
    uses_session=True,
    require_methods=False,
    permission="manage:billing",
    has_translations=True,
    require_reauth=True,
)
class MockBillingViews:
    def __init__(self, organization, request):
        billing_service = request.find_service(IBillingService, context=None)
        if request.flags.enabled(
            AdminFlagValue.DISABLE_ORGANIZATIONS
        ) or not isinstance(billing_service, MockStripeBillingService):
            raise HTTPNotFound
        self.organization = organization
        self.request = request

    @view_config(
        route_name="mock.billing.checkout-session",
        renderer="mock/billing/checkout-session.html",
    )
    def mock_checkout_session(self):
        return {"organization": self.organization}

    @view_config(
        route_name="mock.billing.portal-session",
        renderer="mock/billing/portal-session.html",
    )
    def mock_portal_session(self):
        return {"organization": self.organization}

    @view_config(route_name="mock.billing.trigger-checkout-session-completed")
    def mock_trigger_checkout_session_completed(self):
        mock_event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": self.organization.customer_id,
                    "status": "complete",
                    "subscription": (
                        "mocksub_"
                        + "".join(random.choices(digits + ascii_letters, k=24))
                    ),
                },
            },
        }
        handle_billing_webhook_event(self.request, mock_event)

        return HTTPSeeOther(self.request.route_path("manage.organizations"))
