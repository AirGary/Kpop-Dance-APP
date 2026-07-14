from pydantic import BaseModel, ConfigDict, Field


class IdentityResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
