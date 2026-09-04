from app.schemas.gift_box import GiftBoxState, GiftBoxWorkflowContext
from app.workflows.gift_box.context_resolver import GiftBoxContextResolver


def test_message_overrides_workflow_context_and_existing_state():
    resolved = GiftBoxContextResolver().resolve(
        "Exactly 3 items under Rs. 20,000",
        GiftBoxWorkflowContext(item_count=4, budget_max_lkr=16000, theme="Romantic"),
        GiftBoxState(item_count=2, budget_max_lkr=12000, recipient="friend"),
    )
    assert resolved.item_count == 3
    assert resolved.budget_max_lkr == 20000
    assert resolved.theme == "romantic"
    assert resolved.recipient == "friend"


def test_approximate_item_count_is_not_made_exact():
    resolved = GiftBoxContextResolver().resolve(
        "Around 4 items under Rs. 10,000",
        GiftBoxWorkflowContext(theme="birthday"),
        GiftBoxState(),
    )
    assert resolved.item_count == 4
    assert resolved.item_count_exact is False


def test_missing_context_requires_intent_and_budget():
    assert GiftBoxContextResolver.missing_fields(GiftBoxState()) == [
        "recipient",
        "theme",
        "budget_max_lkr",
    ]
