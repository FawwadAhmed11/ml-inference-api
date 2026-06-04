from contextvars import ContextVar
import uuid
import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse, Response
from prometheus_client import Gauge



IN_FLIGHT_REQUESTS = Gauge(
    "http_requests_in_flight",
    "Number of concurrent HTTP requests currently processing",
    ["method", "handler"]
) 
# Context variable for request ID, isolates each request even when requests run concurrently
request_id_var = ContextVar('request_id', default='no-request-id')

class RequestIdFilter(logging.Filter):
    """Injects request_id from context into every log record."""
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True

def get_request_id():
    return request_id_var.get()

# Middleware
# 2. Middleware to track the lifecycle of every request
# @app.middleware("http")
async def track_in_flight_requests(request: Request, call_next):
    # Get route path or fallback to URL path to avoid high cardinality
    route = request.scope.get("route")
    handler = route.path if route and hasattr(route, "path") else request.url.path

    method = request.method
    
    # Increment the gauge when a request enters
    IN_FLIGHT_REQUESTS.labels(method=method, handler=handler).inc()
    
    try:
        response = await call_next(request)
        return response
    finally:
        # Decrement the gauge when the request leaves (even if it errors out)
        IN_FLIGHT_REQUESTS.labels(method=method, handler=handler).dec()


# @app.middleware("http")
async def add_request_id(request: Request, call_next):
    # check if request id exists
    existing_request_id = request.headers.get("X-Request-ID")
    # generate a new UUID if it's missing
    request_id = existing_request_id if existing_request_id else str(uuid.uuid4())

    
    #store in state
    request.state.request_id = request_id
    request_id_var.set(request_id)

    # Pass the request down the chain to get the response
    response = await call_next(request)
    
    # Return the ID back to the client in headers
    response.headers["X-Request-ID"] = request_id
    
    return response
        

# @app.middleware("http")
async def check_body_size(request: Request, call_next):
    MAX_BODY_SIZE = 1 * 1024 * 1024  # 1 MB in bytes
    # Only check methods that typically have a body
    if request.method in ("POST", "PUT", "PATCH"):
        content_length = request.headers.get("content-length")
        
        if content_length and int(content_length) > MAX_BODY_SIZE:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"detail": "Request body size exceeds the 1 MB limit."}
            )
            
    return await call_next(request)


