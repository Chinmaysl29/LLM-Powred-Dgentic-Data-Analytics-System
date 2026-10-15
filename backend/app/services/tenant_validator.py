"""Tenant validation layer verifying resource ownership, cross-tenant isolation, and authorization."""

from __future__ import annotations

import logging
from typing import Any
import uuid

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


class CrossTenantAccessException(Exception):
    """Raised when an entity belonging to one tenant is accessed by another tenant."""
    pass


class TenantValidator:
    """Enterprise validator ensuring strict isolation and ownership across tenant boundaries."""

    @staticmethod
    def extract_resource_tenant_id(resource: Any) -> str | None:
        """Extract tenant ID from a resource model, dictionary, or attribute."""
        if resource is None:
            return None
        if isinstance(resource, dict):
            tid = resource.get("tenant_id") or resource.get("tenantId")
            return str(tid) if tid is not None else None
        if hasattr(resource, "tenant_id"):
            tid = getattr(resource, "tenant_id")
            return str(tid) if tid is not None else None
        return None

    def validate_ownership(
        self,
        resource: Any,
        request_tenant_id: uuid.UUID | str,
    ) -> bool:
        """Return True if resource belongs to request_tenant_id or system tenant."""
        req_tid = str(request_tenant_id)
        res_tid = self.extract_resource_tenant_id(resource)
        # This equality helper is not a membership check or an admin bypass.
        return bool(res_tid and req_tid and res_tid != "system" and req_tid != "system" and res_tid == req_tid)

    def enforce_access(
        self,
        resource: Any,
        request_tenant_id: uuid.UUID | str,
        resource_description: str = "resource",
    ) -> None:
        """Enforce resource tenancy access, raising HTTP 403 upon cross-tenant access violation."""
        if not self.validate_ownership(resource, request_tenant_id):
            res_tid = self.extract_resource_tenant_id(resource)
            logger.security_warning(
                "CROSS_TENANT_ACCESS_BLOCKED requester_tenant=%s resource_tenant=%s resource_type=%s",
                request_tenant_id,
                res_tid,
                resource_description,
            ) if hasattr(logger, "security_warning") else logger.warning(
                "CROSS_TENANT_ACCESS_BLOCKED requester_tenant=%s resource_tenant=%s resource_type=%s",
                request_tenant_id,
                res_tid,
                resource_description,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: You do not have permission to access this {resource_description}",
            )

    def validate_user_tenant_membership(
        self,
        user: Any,
        tenant_id: uuid.UUID | str,
    ) -> bool:
        """Verify whether a user is an authorized member of the specified tenant."""
        req_tid = str(tenant_id)
        user_tid = getattr(user, "tenant_id", None)
        if user_tid is None or str(user_tid) == "system" or req_tid == "system":
            return False
        return str(user_tid) == req_tid


tenant_validator = TenantValidator()
