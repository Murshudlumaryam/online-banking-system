from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.background_tasks.tasks import write_audit_log_task
from app.core.exceptions import ConflictError
from app.modules.cards.models import Card, CardStatus
from app.modules.cards.repository import CardRepository
from app.modules.customers.models import Customer


class CardService:
    """Customer-facing card operations. Admin-initiated card actions
    (issue, admin-block) live in app.modules.admin.service.AdminService —
    this module is specifically the subset a customer can do to their own
    card without an admin in the loop."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._cards = CardRepository(session)

    async def block_own_card(self, customer: Customer, card: Card) -> Card:
        """Self-service equivalent of a "report lost/stolen card" call to a
        real bank's hotline. Ownership of `card` is verified by the caller
        (see app.modules.cards.dependencies.get_owned_card) before this is
        reached — this method only handles the state transition itself.
        """
        if card.status == CardStatus.BLOCKED:
            raise ConflictError("This card is already blocked")
        if card.status == CardStatus.EXPIRED:
            raise ConflictError("This card has expired and cannot be blocked")

        card.status = CardStatus.BLOCKED
        card.blocked_at = datetime.now(timezone.utc)
        await self._cards.save(card)
        await self._session.commit()

        write_audit_log_task.delay(
            str(customer.user_id), "CUSTOMER_CARD_BLOCKED", "card", str(card.id), None, None
        )
        return card
