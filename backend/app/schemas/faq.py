from pydantic import BaseModel


class FaqArticleOut(BaseModel):
    id: int
    question: str
    answer: str
    category: str | None = None

    model_config = {"from_attributes": True}
