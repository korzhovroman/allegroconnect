# schemas/api.py
from pydantic import BaseModel
from typing import TypeVar, Generic, Optional

T = TypeVar('T')

class APIResponse(BaseModel, Generic[T]):

    success: bool = True
    data: Optional[T] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None