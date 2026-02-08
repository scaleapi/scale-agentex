from typing import Any, Literal

from src.utils.model_utils import BaseModel


class JSONRPCRequest(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    method: str
    params: Any
    id: int | str | None = None


class JSONRPCResponse(BaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    result: Any | None = None
    error: Any | None = None
    id: int | str | None = None


class JSONRPCError(Exception):
    """JSON-RPC 2.0 Error"""

    def __init__(self, code: int, message: str, data: Any | None = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)

    def model_dump(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization"""
        return {"code": self.code, "message": self.message, "data": self.data}
