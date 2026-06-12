import logging
from pythonjsonlogger import jsonlogger
from pythonjsonlogger.json import JsonFormatter
from model_serve.middleware import RequestIdFilter



def setup_json_logging():
    """JSONLogger for python"""
    # Create a handler that outputs to stdout
    handler = logging.StreamHandler()

    # Configure JSON format with custom fields
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
        datefmt="%Y-%m-%dT%H:%M:%SZ"
    )

    handler.setFormatter(formatter)
    # added filter for request ID
    handler.addFilter(RequestIdFilter())
    # Apply to root logger
    logging.root.handlers = [handler]
    logging.root.setLevel(logging.INFO)


#Usage 

setup_json_logging()
logger = logging.getLogger(__name__)
