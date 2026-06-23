import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from services.startup_analyzer import analyze_startup

router = APIRouter()
logger = logging.getLogger("punchstart.api")


class AnalyzeRequest(BaseModel):
    startup_name: str = Field(..., min_length=1, description="Name of the startup")
    industry: str = Field(..., min_length=1, description="Industry sector")
    problem: str = Field(..., min_length=1, description="Problem statement")
    solution: str = Field(..., min_length=1, description="Proposed solution")
    target_customers: str = Field(default="", description="Target customer segment")
    revenue_model: str = Field(default="", description="Revenue model")
    team_size: str = Field(default="", description="Team size")
    funding_requirement: str = Field(default="", description="Funding requirement")
    business_stage: str = Field(default="", description="Current business stage")


@router.post("/validate-startup")
async def analyze_endpoint(request: AnalyzeRequest):
    """
    Accept startup details and return a full investor-grade report.
    """
    try:
        result = await analyze_startup(request.model_dump())
        return result
    except Exception:
        logger.exception("Analysis endpoint failed")
        raise HTTPException(
            status_code=500,
            detail="We could not complete the analysis right now. Please refine the inputs and try again.",
        )
