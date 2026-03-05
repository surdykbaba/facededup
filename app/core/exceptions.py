from fastapi import Request
from fastapi.responses import JSONResponse


class FaceDeduplicationError(Exception):
    status_code: int = 500
    detail: str = "Internal server error"

    def __init__(self, detail: str | None = None):
        if detail:
            self.detail = detail
        super().__init__(self.detail)


class NoFaceDetectedError(FaceDeduplicationError):
    status_code = 400
    detail = "No face detected in the image"


class MultipleFacesError(FaceDeduplicationError):
    status_code = 400
    detail = "Multiple faces detected; expected exactly one"


class InvalidImageError(FaceDeduplicationError):
    status_code = 400
    detail = "Invalid or corrupted image"


class ImageTooLargeError(FaceDeduplicationError):
    status_code = 413
    detail = "Image exceeds maximum allowed size"


class RecordNotFoundError(FaceDeduplicationError):
    status_code = 404
    detail = "Record not found"


class LivenessCheckFailedError(FaceDeduplicationError):
    status_code = 422
    detail = "Image failed liveness/quality checks"


async def face_error_handler(
    request: Request, exc: FaceDeduplicationError
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.__class__.__name__, "detail": exc.detail},
    )
