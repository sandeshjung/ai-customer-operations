from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.product import Product
from app.schemas.product import ProductCreate, ProductResponse

router = APIRouter(
    prefix="/products",
    tags=["Products"]
)

@router.post(
    "",
    response_model=ProductResponse,
)
def create_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
):
    product = Product(
        name=data.name,
        description=data.description,
        price=data.price,
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    return product

@router.get(
    "/{product_id}",
    response_model=ProductResponse,
)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    return product
