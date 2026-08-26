"""Identity links — the Slack/Linear user -> SGP user mapping, plus that user's
stored SGP credential.

Why this exists: an event-driven invocation arrives with only a provider-side
identity (a Slack ``U…`` in a team). Nothing about that can be *computed* into an
SGP user, and nothing in a webhook proves anything about SGP. So the mapping has
to be established out-of-band, in a moment where both identities are
authenticated at once, and recorded here.

Why a credential is stored alongside it: reading a user's connected integrations
(their Notion, their Linear) from the secrets service requires authenticating *as
that user* — the owner is derived from the caller, never passed as a parameter.
At webhook time the user isn't present, so their credential has to be held. The
key is minted with an expiry precisely so what's held is bounded.

The ciphertext is deliberately NOT a field on this entity. This object gets
logged, cached, and passed around; the credential is fetched through a separate,
narrow repository call on the one path that needs it. Keeping them apart means a
stray log line or a cache dump can't leak a key.
"""

from datetime import datetime
from enum import Enum

from pydantic import Field

from src.utils.model_utils import BaseModel


class IdentityProvider(str, Enum):
    SLACK = "slack"
    LINEAR = "linear"


class IdentityLinkMethod(str, Enum):
    """How a link was established — i.e. how much to trust it.

    ``explicit``    the user proved both sides: a signed Slack event established
                    the provider identity, an authenticated browser session
                    established the SGP identity. Strongest.
    ``email_match`` a shared IdP already established they're the same human and
                    email was the join key. Only as good as the IdP, and only if
                    guests and external members are excluded.
    ``manual``      an operator asserted it. No cryptographic proof; used for
                    bootstrap and testing, and visible as such.
    """

    EXPLICIT = "explicit"
    EMAIL_MATCH = "email_match"
    MANUAL = "manual"


class IdentityLinkEntity(BaseModel):
    id: str = Field(..., description="The unique identifier of the link.")
    provider: IdentityProvider = Field(
        ..., description="Which external provider this identity belongs to."
    )
    external_team_id: str = Field(
        ...,
        description=(
            "Provider-side tenant: Slack team_id / Linear org id. Part of the "
            "identity because a bare user id is only unique within its workspace."
        ),
    )
    external_user_id: str = Field(
        ..., description="Provider-side user id (e.g. a Slack U... id)."
    )
    sgp_user_id: str = Field(..., description="The SGP user this identity maps to.")
    sgp_account_id: str = Field(
        ..., description="The SGP account the mapped user acts within."
    )
    linked_via: IdentityLinkMethod = Field(
        ..., description="How this link was established (its trust level)."
    )
    has_credential: bool = Field(
        False,
        description=(
            "Whether a stored SGP credential exists for this link. A boolean, not "
            "the credential: callers need to know if the agent can act as this "
            "user without the key entering scope."
        ),
    )
    credential_expires_at: datetime | None = Field(
        None,
        description=(
            "When the stored credential stops working. Checked before use so an "
            "expired key produces a re-link prompt rather than a confusing 401 "
            "from the secrets service."
        ),
    )
    linked_at: datetime | None = Field(None, description="When the link was created.")
    revoked_at: datetime | None = Field(
        None,
        description=(
            "Set when the link is revoked. NULL means active; rows are tombstoned "
            "rather than deleted so unlinks stay auditable."
        ),
    )

    def credential_is_usable(self, *, now: datetime) -> bool:
        """Whether the agent can currently act as this user.

        A link with no credential is still a valid mapping — useful for
        attribution — it just can't be acted through. An expired one is treated
        the same as absent, and the caller prompts a re-link.
        """
        if self.revoked_at is not None or not self.has_credential:
            return False
        if self.credential_expires_at is None:
            return True
        return self.credential_expires_at > now
