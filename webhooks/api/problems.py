from rest_framework.views import exception_handler

PROBLEM_CONTENT_TYPE = "application/problem+json"


def problem_details_handler(exc, context):
    """Turns DRF errors into RFC 9457 Problem Details with a stable ``code``."""
    response = exception_handler(exc, context)
    if response is None:
        return None

    data = response.data
    body = {"type": "about:blank", "title": response.status_text, "status": response.status_code}
    if isinstance(data, dict) and set(data) == {"detail"}:
        body["detail"] = str(data["detail"])
        body["code"] = getattr(data["detail"], "code", "error")
    else:
        body["detail"] = "Invalid request."
        body["code"] = "invalid"
        body["errors"] = data

    response.data = body
    response.content_type = PROBLEM_CONTENT_TYPE
    return response
