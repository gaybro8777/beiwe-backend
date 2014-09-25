from flask import request, abort
from libs.db_models import User
import functools


def authenticate_user(some_function):
    """Decorator for functions (pages) that require a user to provide identification.
       Returns 403 (forbidden) if the identifying info (usernames, passwords
       device IDs are invalid."""
    @functools.wraps(some_function)
    def wrapped(*args, **kwargs):
        is_this_user_valid = validate_post( *args, **kwargs )
        if is_this_user_valid: return some_function(*args, **kwargs)
        return abort(403)
    return wrapped


def validate_post( *args, **kwargs ):
    """Check if user exists, check if the provided passwords match"""
    if not User.exists(request.values['patient_id']): return False
    user = User( request.values['patient_id'] )
    
    if not user.validate_password( request.values['password'] ): return False
    if not user['device_id'] == request.values['device_id']: return False
    
    return True
