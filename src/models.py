from dataclasses import dataclass


@dataclass # This decorator automatically generates special methods for the class.
# the data object that flows through the system
class Request:
    request_id: int # unique identifier for the request
    client_id: str # identifier for the client making the request
    resource_key: str # key representing the resource being requested (e.g., "user:42")