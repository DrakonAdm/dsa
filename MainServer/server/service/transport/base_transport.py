from pydantic import BaseModel, ConfigDict, Field
from typing import Optional


class ModelConfigInternal(BaseModel):
    id: int
    name: str
    type: str
    endpoint_url: str
    is_active: bool
    model_config = ConfigDict(from_attributes=True)

class ModelConfigBase(BaseModel):
    id: int
    name: str
    type: str
    model_config = ConfigDict(from_attributes=True)


class CallbackPayload(BaseModel):
    success: bool
    error: Optional[str] = None
    processing_time_ms: float
    is_segmentation: bool
    model_type: str
    result: Optional[dict] = None
    task_id: Optional[str] = Field(..., description="ID задачи с основного сервиса")


class WSCommand:
    """Константы команд клиента."""
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    START_ANALYSIS = "start_analysis"
    CANCEL_TASK = "cancel_task"
    PING = "ping"
