import os
import shutil
import uuid
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from backend.schemas import AnalysisResponse
from backend.services.pipeline_service import process_images

router = APIRouter(tags=["analysis"])

# Absolute path so uploads work regardless of the CWD at launch time
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
UPLOAD_DIR = os.path.abspath(UPLOAD_DIR)
os.makedirs(UPLOAD_DIR, exist_ok=True)

_MAX_IMAGES = 5


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze(
    images: List[UploadFile] = File(..., description="1–5 drug-package images"),
    expected_drug_name: Optional[str] = Form(None),
    expected_batch_number: Optional[str] = Form(None),
    expected_expiry_date: Optional[str] = Form(None),
    expected_manufacturer: Optional[str] = Form(None),
):
    """
    Analyse one or more drug-package images.

    Supply up to 5 images (different sides of the same package) for the
    best extraction coverage.  Results are merged so batch numbers from
    a side panel and brand names from the front face complement each other.
    """
    if not images:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one image file is required.",
        )
    if len(images) > _MAX_IMAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {_MAX_IMAGES} images allowed per request.",
        )

    saved_paths: List[str] = []
    for img in images:
        content_type = (img.content_type or "").lower()
        if not content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{img.filename}' is not an image.",
            )
        extension = os.path.splitext(img.filename or "")[1] or ".jpg"
        file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}{extension}")
        with open(file_path, "wb") as buf:
            shutil.copyfileobj(img.file, buf)
        saved_paths.append(file_path)

    expected_data = {
        "drug_name": expected_drug_name,
        "batch_number": expected_batch_number,
        "expiry_date": expected_expiry_date,
        "manufacturer": expected_manufacturer,
    }

    return process_images(saved_paths, expected_data)
