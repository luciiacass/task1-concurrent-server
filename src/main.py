import time

from models import Request
from server import Server


def main():
    # Create a server with X workers
    # case 1: low concurrency, no waiting, no cache hits
    #server = Server(num_workers=1, max_active_workers=1, cache_ttl=15)
    # case 2: high concurrency, waiting, cache hits
    #server = Server(num_workers=4, max_active_workers=2, cache_ttl=15)
    # case 3: high concurrency, waiting, cache hits
    server = Server(num_workers=6, max_active_workers=6, cache_ttl=15)
    # Start the server
    server.start()

    # Simulate incoming requests
    requests = [
        Request(1, "C1", "user:1"),
        Request(2, "C2", "user:1"),
        Request(3, "C3", "user:1"),
        Request(4, "C4", "user:1"),
        Request(5, "C5", "user:1"),
        Request(6, "C6", "user:1"),
    ]

    # Submit requests to the server with a small delay to simulate real-world conditions
    for req in requests:
        server.submit_request(req)
        time.sleep(0)

    time.sleep(10)
    # Stop the server and print statistics
    server.stop()
    server.print_stats()


if __name__ == "__main__":
    main()
    