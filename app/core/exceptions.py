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

    def __init__(self, detail: str | None = None, liveness_info: dict | None = None):
        self.liveness_info = liveness_info
        super().__init__(detail)


class InsufficientFramesError(FaceDeduplicationError):
    status_code = 400
    detail = "Multi-frame liveness requires 3-5 image frames"


class DuplicateFramesError(FaceDeduplicationError):
    status_code = 400
    detail = "Duplicate or near-duplicate frames detected"


async def face_error_handler(
    request: Request, exc: FaceDeduplicationError
) -> JSONResponse:
    content: dict = {"error": exc.__class__.__name__, "detail": exc.detail}

    # Include full liveness breakdown so callers know exactly what failed
    if isinstance(exc, LivenessCheckFailedError) and exc.liveness_info:
        info = exc.liveness_info

        # Build a concise per-check summary
        failed_checks = []
        passed_checks = []
        checks = info.get("checks", {})
        for name, check in checks.items():
            entry = {
                "name": name,
                "passed": check["passed"],
                "score": check["score"],
                "detail": check["detail"],
                "mandatory": check["mandatory"],
            }
            if check["passed"]:
                passed_checks.append(entry)
            else:
                failed_checks.append(entry)

        content["liveness"] = {
            "is_live": info.get("is_live", False),
            "liveness_score": info.get("liveness_score", 0),
            "checks_passed": info.get("checks_passed", 0),
            "checks_total": info.get("checks_total", 0),
            "mandatory_passed": info.get("mandatory_checks_passed", 0),
            "mandatory_total": info.get("mandatory_checks_total", 0),
            "failed_checks": failed_checks,
            "passed_checks": passed_checks,
        }

    return JSONResponse(
        status_code=exc.status_code,
        content=content,
    )
