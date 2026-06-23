def create_app(*args, **kwargs):
    from .api import create_app as api_create_app

    return api_create_app(*args, **kwargs)


__all__ = ["create_app"]
