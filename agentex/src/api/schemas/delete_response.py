from src.utils.model_utils import BaseModel


class DeleteResponse(BaseModel):
    id: str
    message: str
