# Concurrent HTTP Server with Thread-Safe Cache

## Description

Multithreaded HTTP server in Python that processes client requests using its own worker pool and a shared in-memory cache.

## Features

- Raw socket HTTP server, without `http.server` or built-in HTTP worker pools
- Concurrent request processing
- Thread-safe queue and cache
- TTL-based caching
- No duplicate computation for same resource
- Synchronization with Lock, Condition, Semaphore
- Thread-safe logging
- Counts uppercase letters in requested text files

## How to Run

```bash
python src/main.py
```

Then request a file:

```bash
curl http://localhost:10001/test.txt
```

The example URL uses port `10001`. 

## Concurrent Client

Run this in another terminal while the server is active:

```bash
python src/concurrency_client.py --url http://localhost:10001/test.txt --requests 20 --concurrency 10
```

## Architecture

- HTTP acceptor -> accepts TCP connections and enqueues sockets
- Workers -> parse HTTP requests, count uppercase letters, and send responses
- Cache -> stores computed file results

## Cache Behavior

- HIT -> reuse result
- MISS -> compute result
- WAIT -> wait for another worker computing the same file

## Notes

- Designed for no-GIL environments
- All shared resources are explicitly synchronized
