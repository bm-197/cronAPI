from fastapi import HTTPException

class APIError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code
        self.message = message

def error_response(err):
    if isinstance(err, APIError):
        return HTTPException(status_code=err.status_code, detail=err.message)
    return HTTPException(status_code=500, detail=str(err)) 