import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.routes.analyze import router as analyze_router

app = FastAPI()
logger = logging.getLogger("exdav.backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# allow React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"message": "Ex-DAV Backend Running"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled backend error for %s", request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "verdict": "Inconclusive",
            "confidence": 0.0,
            "explanation": [
                "The system encountered an internal error, so the result is inconclusive."
            ],
            "metadata": {
                "drug_name": "",
                "dosage": "",
                "manufacturer": "",
                "batch_number": "",
                "manufactured_date": "",
                "expiry_date": "",
                "detected_logos": [],
            },
            "validationResults": [
                {
                    "guideline": "NMRA",
                    "rule": "System reliability check",
                    "status": "failed",
                    "detail": "Analysis pipeline failed before completion.",
                    "severity": "error",
                }
            ],
            "trustScore": 0.0,
            "conflictingClues": True,
            "ocr_raw_text": "",
            "featureImportances": {},
            "nmra_status": "Unavailable",
            "manufacturer_match": False,
            "number_of_images_processed": 0,
            "nmra": {
                "status": "Unavailable",
                "display_status": "UNAVAILABLE",
                "record": None,
                "extracted_manufacturer": "",
                "nmra_manufacturer": "",
                "validation": {
                    "manufacturer_match": False,
                    "brand_match": None,
                    "dosage_match": None,
                },
                "summary_text": "Analysis failed before NMRA verification could complete.",
            },
        },
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning("Request validation failed for %s: %s", request.url.path, exc.errors())
    return JSONResponse(
        status_code=400,
        content={
            "verdict": "Inconclusive",
            "confidence": 0.0,
            "explanation": [
                "Input validation failed. Please upload a valid drug package image."
            ],
            "metadata": {
                "drug_name": "",
                "dosage": "",
                "manufacturer": "",
                "batch_number": "",
                "manufactured_date": "",
                "expiry_date": "",
                "detected_logos": [],
            },
            "validationResults": [
                {
                    "guideline": "NMRA",
                    "rule": "Submission requires valid image evidence",
                    "status": "failed",
                    "detail": "Image is missing or invalid in request payload.",
                    "severity": "error",
                }
            ],
            "trustScore": 0.0,
            "conflictingClues": True,
            "ocr_raw_text": "",
            "featureImportances": {},
            "nmra_status": "Unavailable",
            "manufacturer_match": False,
            "number_of_images_processed": 0,
            "nmra": {
                "status": "Unavailable",
                "display_status": "UNAVAILABLE",
                "record": None,
                "extracted_manufacturer": "",
                "nmra_manufacturer": "",
                "validation": {
                    "manufacturer_match": False,
                    "brand_match": None,
                    "dosage_match": None,
                },
                "summary_text": "Request invalid; NMRA verification was not performed.",
            },
        },
    )


app.include_router(analyze_router)