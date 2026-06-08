"""REST client for Spark AuthZ (SpiceDB) via its HTTP-transcoded gRPC API.

Production services often use native gRPC to Spark AuthZ; this suite uses the
HTTP-transcoded routes from the proto annotations instead so we can exercise
the same RPCs with httpx only (no generated stubs or extra wiring here).
"""

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SUBJECT_TYPE_IDENTITY = "identity"
SUBJECT_TYPE_SERVICE = "service_identity"


@dataclass(frozen=True)
class SparkAuthzConfig:
    host: str
    use_tls: bool = False

    @property
    def base_url(self) -> str:
        scheme = "https" if self.use_tls else "http"
        return f"{scheme}://{self.host}"


class SparkAuthzClient:
    """HTTP client for the Spark AuthZ ResourceService REST API."""

    def __init__(self, config: SparkAuthzConfig, timeout: float = 10.0) -> None:
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )

    def check_permission(
        self,
        subject_id: str,
        resource_type: str,
        resource_id: str,
        permission: str,
        subject_type: str = SUBJECT_TYPE_IDENTITY,
    ) -> dict[str, bool]:
        """Check one or more permissions. Returns {permission: bool} map."""
        payload = {
            "subject_type": subject_type,
            "subject_id": subject_id,
            "permission": permission,
            "resource_type": resource_type,
            "resource_id": resource_id,
        }
        resp = self._client.post("/v1/resources/check/permission", json=payload)
        resp.raise_for_status()
        return resp.json().get("permissions", {})

    def check_permission_bool(
        self,
        subject_id: str,
        resource_type: str,
        resource_id: str,
        permission: str,
        subject_type: str = SUBJECT_TYPE_IDENTITY,
    ) -> bool:
        """Convenience: check a single permission and return True/False."""
        perms = self.check_permission(
            subject_id, resource_type, resource_id, permission, subject_type
        )
        return perms.get(permission, False)

    def get_resource_access(
        self,
        resource_type: str,
        resource_id: str,
        subject_id: str,
        subject_type: str = SUBJECT_TYPE_IDENTITY,
    ) -> list[dict[str, str]]:
        """Get the access list for a resource. Returns list of entries."""
        payload = {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "subject_type": subject_type,
            "subject_id": subject_id,
        }
        resp = self._client.post("/v1/resources/access/list", json=payload)
        resp.raise_for_status()
        return resp.json().get("entries", [])

    def grant_access(
        self,
        resource_type: str,
        resource_id: str,
        subject_id: str,
        relation: str,
        grantee_id: str,
        grantee_type: str = SUBJECT_TYPE_IDENTITY,
        subject_type: str = SUBJECT_TYPE_IDENTITY,
    ) -> httpx.Response:
        """Grant a relation on a resource. Returns raw response for error checking."""
        payload = {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "relation": relation,
            "grantee_type": grantee_type,
            "grantee_id": grantee_id,
        }
        resp = self._client.post("/v1/resources/access/grant", json=payload)
        logger.debug(
            "grant_access %s:%s %s->%s -> %d",
            resource_type,
            resource_id,
            relation,
            grantee_id,
            resp.status_code,
        )
        return resp

    def revoke_access(
        self,
        resource_type: str,
        resource_id: str,
        subject_id: str,
        grantee_id: str,
        relation: str = "",
        grantee_type: str = SUBJECT_TYPE_IDENTITY,
        subject_type: str = SUBJECT_TYPE_IDENTITY,
    ) -> httpx.Response:
        """Revoke a relation (or all relations if relation is empty)."""
        payload: dict[str, Any] = {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "grantee_type": grantee_type,
            "grantee_id": grantee_id,
        }
        if relation:
            payload["relation"] = relation
        resp = self._client.post("/v1/resources/access/revoke", json=payload)
        logger.debug(
            "revoke_access %s:%s %s from %s -> %d",
            resource_type,
            resource_id,
            relation or "(all)",
            grantee_id,
            resp.status_code,
        )
        return resp

    def create_resource(
        self,
        resource_type: str,
        resource_id: str,
        subject_id: str,
        tenant_id: str,
        subject_type: str = SUBJECT_TYPE_IDENTITY,
    ) -> httpx.Response:
        """Create a resource in the authorization graph."""
        payload = {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "tenant_id": tenant_id,
        }
        resp = self._client.post("/v1/resources/create", json=payload)
        logger.debug(
            "create_resource %s:%s -> %d", resource_type, resource_id, resp.status_code
        )
        return resp

    def delete_resource(
        self,
        resource_type: str,
        resource_id: str,
        subject_id: str,
        subject_type: str = SUBJECT_TYPE_IDENTITY,
    ) -> httpx.Response:
        """Delete a resource from the authorization graph."""
        payload = {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "subject_type": subject_type,
            "subject_id": subject_id,
        }
        resp = self._client.post("/v1/resources/delete", json=payload)
        logger.debug(
            "delete_resource %s:%s -> %d", resource_type, resource_id, resp.status_code
        )
        return resp

    def lookup_resources(
        self,
        resource_type: str,
        permission: str,
        subject_id: str,
        tenant_id: str,
        subject_type: str = SUBJECT_TYPE_IDENTITY,
    ) -> list[str]:
        """Lookup all resource IDs accessible by a subject. Returns list of IDs."""
        payload = {
            "resource_type": resource_type,
            "permission": permission,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "tenant_id": tenant_id,
        }
        resp = self._client.post("/v1/resources/lookup", json=payload)
        resp.raise_for_status()
        return resp.json().get("resource_ids", [])

    def close(self) -> None:
        self._client.close()
