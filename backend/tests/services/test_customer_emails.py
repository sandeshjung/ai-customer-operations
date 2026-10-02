from app.agents.models import TriageAction
from app.core.config import settings
from app.services import customer_emails


def test_status_link_opens_the_order_in_the_portal(monkeypatch):
    monkeypatch.setattr(settings, "CUSTOMER_PORTAL_URL", "https://track.example.com/")

    assert customer_emails.order_status_url(42) == "https://track.example.com/?order=42"


def test_acknowledgement_has_view_status_link_in_text_and_html():
    email = customer_emails.ticket_acknowledgement("Jane", 7, 42, about="your order")

    url = customer_emails.order_status_url(42)
    assert "#7" in email.subject
    assert email.text.startswith("Hi Jane,")
    assert f"View status: {url}" in email.text
    assert "View status</a>" in email.html
    assert f'href="{url}"' in email.html


def test_html_escapes_customer_supplied_text():
    email = customer_emails.ticket_acknowledgement(
        "Jane", 7, 42, about="<script>alert(1)</script>"
    )

    assert "<script>" not in email.html
    assert "&lt;script&gt;" in email.html


def test_order_update_text_is_unchanged_without_a_ticket():
    email = customer_emails.order_update("Your parcel is moving.", 42, ticket_id=None)

    assert email.text == "Your parcel is moving."
    assert "View status</a>" in email.html


def test_order_update_mentions_ticket_when_one_was_opened():
    email = customer_emails.order_update("We're on it.", 42, ticket_id=9)

    assert email.text.startswith("We're on it.")
    assert "ticket #9" in email.text
    assert customer_emails.order_status_url(42) in email.text


def test_triage_update_wording_follows_outcome():
    def subject(action, resolved=False):
        return customer_emails.triage_update(
            "Jane", 5, 42, action=action, resolved=resolved
        ).subject

    assert "resolved" in subject(TriageAction.RESOLVE, resolved=True)
    assert "escalated" in subject(TriageAction.ESCALATE)
    assert "support team" in subject(TriageAction.ROUTE_TO_AGENT)
    # RESOLVE that triage didn't actually close (needs a human) isn't "resolved".
    assert "support team" in subject(TriageAction.RESOLVE, resolved=False)
    assert "reviewed" in subject(TriageAction.AUTO_RESPOND)
