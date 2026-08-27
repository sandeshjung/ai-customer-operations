from fastapi import FastAPI

from app.api.customers import router as customers_router
from app.api.orders import router as orders_router
from app.api.products import router as products_router
from app.api.shipments import router as shipments_router

from app.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="AI Customer Operations automation platform",
    debug=settings.DEBUG
)

app.include_router(customers_router, prefix=settings.API_V1_PREFIX)
app.include_router(orders_router, prefix=settings.API_V1_PREFIX)
app.include_router(products_router, prefix=settings.API_V1_PREFIX)
app.include_router(shipments_router, prefix=settings.API_V1_PREFIX)

@app.get("/health")
async def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "environment": settings.APP_ENV,
    }