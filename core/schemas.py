"""Request/response shapes. ParsedQuery is the important one."""
from typing import Literal

from pydantic import BaseModel, Field

PrefType = Literal["priority", "indifferent", "sacrifice"]


class AspectPreference(BaseModel):
    aspect: str
    kind: PrefType
    weight: float = 1.0  # only meaningful for 'priority'


class HardConstraints(BaseModel):
    max_price: float | None = None
    min_price: float | None = None
    brands_include: list[str] = Field(default_factory=list)
    brands_exclude: list[str] = Field(default_factory=list)


class ParsedQuery(BaseModel):
    """Output of the NLP layer.

    'indifferent' means the aspect does not affect ranking.
    'sacrifice' means the same -- BUT a floor is enforced.
    Collapsing these two is exactly the failure this project addresses.
    """
    raw_text: str
    constraints: HardConstraints = Field(default_factory=HardConstraints)
    preferences: list[AspectPreference] = Field(default_factory=list)

    def priorities(self) -> dict[str, float]:
        return {p.aspect: p.weight for p in self.preferences
                if p.kind == "priority"}

    def sacrifices(self) -> list[str]:
        return [p.aspect for p in self.preferences if p.kind == "sacrifice"]


class AspectEvidence(BaseModel):
    aspect: str
    label: str
    score: float
    confidence: float
    mentions: int
    snippet: str | None = None


class Recommendation(BaseModel):
    product_id: str
    title: str
    price: float | None
    image_url: str | None
    utility: float
    floor_penalty: float
    aspects: list[AspectEvidence]
    explanation: str


class RecommendRequest(BaseModel):
    query: str
    top_k: int = 10
    use_floor: bool = True   # flip to False for the ablation


class RecommendResponse(BaseModel):
    parsed: ParsedQuery
    floors: dict[str, float]
    results: list[Recommendation]
    