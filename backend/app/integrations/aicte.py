"""AICTE integration adapter.

IMPORTANT: No official AICTE API endpoint, schema or credential process has been verified in this MVP.
This adapter is a clearly marked placeholder. It never returns fabricated data and never reports 'connected'.
Replace fetch_institutions() once an authorized, documented source is confirmed with AICTE.
"""
from ..config import AICTE_API_BASE, AICTE_API_KEY

class AicteAdapter:
    name = "AICTE institution directory"
    type = "official-source (not yet connected)"

    def configured(self) -> bool:
        return bool(AICTE_API_BASE and AICTE_API_KEY)

    def status(self, imports_done: int) -> dict:
        credentials_present = self.configured()
        if not credentials_present:
            state = "Credentials required"
        else:
            state = "Configured - adapter not implemented"  # we never claim 'Connected' without a verified call
        return {"name": self.name, "type": self.type, "state": state,
                "last_sync": None, "imports_done": imports_done,
                "credentials_present": credentials_present,
                "official_documentation_verified": False,
                "endpoint_verified": False,
                "response_schema_verified": False,
                "authorized_access_verified": False,
                "working_response_verified": False,
                "note": ("Import officially obtained CSV/XLSX files from the Import page." if imports_done == 0 else
                          "Data present via manual import (not a live sync).")}

    def lookup_institutions(self, query: str) -> dict:
        """Query external directory for institution suggestions.
        Requires verified credentials; returns suggestions requiring review before save.
        Never fabricates results or claims official verification.
        """
        q = (query or "").strip()
        if not q:
            return {
                "available": False,
                "configured": self.configured(),
                "source_name": self.name,
                "source_type": self.type,
                "message": "Please enter an institution name or AICTE ID to search.",
                "suggestions": []
            }

        if not self.configured():
            return {
                "available": False,
                "configured": False,
                "source_name": self.name,
                "source_type": self.type,
                "message": "External AICTE directory lookup is unavailable: verified API credentials (AICTE_API_BASE and AICTE_API_KEY) are required. Manual registration remains fully available.",
                "suggestions": []
            }

        return {
            "available": False,
            "configured": True,
            "source_name": self.name,
            "source_type": self.type,
            "message": "AICTE API credentials are configured, but the live endpoint adapter is pending official AICTE schema confirmation. Manual registration is active.",
            "suggestions": []
        }

    def fetch_institutions(self):
        raise NotImplementedError("No verified official AICTE API available. Use CSV/XLSX import.")
