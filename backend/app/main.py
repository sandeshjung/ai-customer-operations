from app.api.customers import router as customers_router
from app.api.orders import router as orders_router
from app.api.products import router as products_router
from app.api.shipments import router as shipments_router
from app.api.tickets import router as tickets_router
from app.core.config import settings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.logging import configure_logging
from app.core.tracing import setup_tracing
from app.api.health import router as health_router
from app.api.admin import router as admin_router

configure_logging()
setup_tracing()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="AI Customer Operations automation platform",
    debug=settings.DEBUG,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(customers_router, prefix=settings.API_V1_PREFIX)
app.include_router(orders_router, prefix=settings.API_V1_PREFIX)
app.include_router(products_router, prefix=settings.API_V1_PREFIX)
app.include_router(shipments_router, prefix=settings.API_V1_PREFIX)
app.include_router(tickets_router, prefix=settings.API_V1_PREFIX)
app.include_router(health_router, prefix=settings.API_V1_PREFIX)
app.include_router(admin_router, prefix=settings.API_V1_PREFIX)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {
        "status": "healthy",
        "environment": settings.APP_ENV,
    }
