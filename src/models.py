from dataclasses import dataclass
import socket


# This decorator automatically generates special methods for the class.
@dataclass
# the data object that flows through the system
class Request:
    request_id: int  # unique identifier for the request
    client_address: tuple[str, int]  # (IP address, port) of the client making the request
    client_socket: socket.socket  # socket object representing the connection to the client
    # simulation -> client_id: str # identifier for the client making the request
    resource_key: str  # key representing the resource being requested (e.g., "test.txt")
