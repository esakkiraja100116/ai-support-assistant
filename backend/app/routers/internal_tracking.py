"""Mock internal shipment-tracking API. Deliberately unauthenticated - this
simulates a service that would sit behind network-level access control
(VPC/internal-only ingress) in a real deployment, not exposed publicly; for
this demo, the simplest faithful stand-in is an internal-only route with no
auth dependency, called over real HTTP (not in-process) so the caller's
timeout/retry/circuit-breaker logic exercises a real request cycle.
"""
from fastapi import APIRouter, HTTPException

from app.services.tracking_fixtures import TRACKING_FIXTURES

router = APIRouter(prefix="/internal/tracking", tags=["internal"])


@router.get("/{awb_number}")
def get_tracking_mock(awb_number: str) -> dict:
    fixture = TRACKING_FIXTURES.get(awb_number)
    if fixture is None:
        raise HTTPException(status_code=404, detail="AWB not found")
    return fixture
