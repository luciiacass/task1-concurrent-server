# Concurrent Server with Thread-Safe Cache

## Description

Multithreaded server in Python that processes client requests using a worker pool and a shared in-memory cache.

## Features

- Concurrent request processing
- Thread-safe queue and cache
- TTL-based caching
- No duplicate computation for same resource
- Synchronization with Lock, Condition, Semaphore
- Thread-safe logging

## How to Run

```bash
python main.py
```

## Architecture

- Producer → receives requests
- Workers → process requests from queue
- Cache → stores computed results

## Cache Behavior

- HIT → reuse result
- MISS → compute result
- WAIT → wait for another thread

## Notes

- Designed for no-GIL environments
- All shared resources are explicitly synchronized
