from rest_framework.exceptions import APIException

class NotSupportType(APIException):
    """
    Raised the problem given isn't supported.
    """
    status_code = 400
    default_detail = "The problem type is not support."
