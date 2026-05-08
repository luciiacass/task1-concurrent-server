from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

# ThreadPoolExecuter used to create concurrent clients for testing the server. 


# Send one HTTP request and return timing plus parsed JSON payload.
def fetch(url: str, request_id: int) -> dict:
    # Measure each individual request duration.
    started = time.perf_counter()
    try:
        # Open TCP conexion and send the HTTP request
        with urllib.request.urlopen(url, timeout=10) as response:
            body = response.read().decode("utf-8")
            payload = json.loads(body)
            status = response.status
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8"))
        status = exc.code

    # Allows the analysis the response  
    return {
        "request_id": request_id,
        "status": status,
        "elapsed": time.perf_counter() - started,
        "payload": payload,
    }


def main() -> None:
    # Configure the concurrent client from command-line arguments.
    parser = argparse.ArgumentParser(description="Concurrent HTTP client for the custom worker-pool server.")
    # URL requested by every client thread.
    parser.add_argument("--url", default="http://localhost:10001/test.txt")
    # Total number of HTTP requests to send.
    parser.add_argument("--requests", type=int, default=20)
    # Number of client threads used to send requests in parallel.
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    # Measure the total client test duration.
    started = time.perf_counter()
    # ThreadPoolExecutor creates concurrent clients for testing the server.
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        # Submit all HTTP requests at once.
        futures = [
            executor.submit(fetch, args.url, request_id)
            for request_id in range(1, args.requests + 1)
        ]

        for future in as_completed(futures):
            result = future.result()
            payload = result["payload"]
            # Show which server worker answered and whether the value came from cache.
            print(
                f"#{result['request_id']:02d} "
                f"status={result['status']} "
                # 200 = ok, 404 = not found, 500 = server error
                f"elapsed={result['elapsed']:.3f}s "
                f"worker={payload.get('worker')} "
                f"cached={payload.get('cached')} " 
                #if cache = true the value came from cache, if cache = false the value was computed by the worker.
                f"uppercase={payload.get('uppercase_letters')}"
                # result
            )

    print(f"\nCompleted {args.requests} requests in {time.perf_counter() - started:.3f}s")


if __name__ == "__main__":
    main()
