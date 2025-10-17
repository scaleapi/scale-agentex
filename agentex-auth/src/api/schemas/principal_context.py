from pydantic import RootModel

from src.domain.models.principal_contexts import SGPPrincipalContext


class PrincipalContext(RootModel):
    root: SGPPrincipalContext  # make into union with other providers
