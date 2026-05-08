from server import Server

# configuration of HTTP server and the pool worker
def main() -> None:
    # Create a server with X workers
    # case 1: low concurrency, no waiting, no cache hits
    # num_workers=1, max_active_workers=1, cache_ttl=15
    # case 2: high concurrency, waiting, cache hits
    # num_workers=4, max_active_workers=2, cache_ttl=15
    # case 3: high concurrency, waiting, cache hits
    server = Server(
        host="127.0.0.1", # The server will listen locally
        port=10001,
        num_workers=6,
        max_active_workers=6,
        cache_ttl=15,
        files_dir="files",
    )
    # Start the server and keep it running until Ctrl+C.
    server.serve_forever()


if __name__ == "__main__":
    main()


# It is normal that DONE is shown after HIT, because the server processes requests concurrently.
