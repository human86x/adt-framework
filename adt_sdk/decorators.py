from functools import wraps
from typing import Dict, Any, Optional
from .client import ADTClient

def adt_authorized(spec_id: str, action: str, rationale: str = "Authorized action"):
    """
    Decorator to wrap a function that performs a protected action.
    The wrapped function must return the params for the DTTP request.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Assume self is the first arg and has an adt_client
            client: ADTClient = args[0].adt_client
            
            # Call the function to get params
            params = func(*args, **kwargs)
            
            # Submit to ADT
            return client.request(spec_id, action, params, rationale)
        return wrapper
    return decorator
