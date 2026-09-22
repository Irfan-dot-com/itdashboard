from fastapi import APIRouter, Depends

from app.database import Database, get_db
from app.lib.ingestor import Ingestor
from app.schemas.ingest import IngestRequest, IngestResponse

router = APIRouter()


@router.post("/v1/edge/ingest", response_model=IngestResponse)
async def ingest(body: IngestRequest, db: Database = Depends(get_db)):
    async with db.acquire() as conn:
        ingestor = Ingestor(conn)
        result = await ingestor.handle_batch(
            edge_id=body.edge_id,
            service_provider=body.service_provider,
            property_id=body.property_id,
            property_name=body.property_name,
            messages=body.messages,
        )
    return IngestResponse(edge_id=body.edge_id, **result)
