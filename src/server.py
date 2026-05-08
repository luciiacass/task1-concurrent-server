from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from cache import ThreadSafeCache
from logger_setup import setup_logger
from models import Request
from request_queue import RequestQueue


# "a pool of worker threads performs the processing"
# server that:
# - create multiple workers
# - the workers wait for request
# - when the workers receive a request, they process it

class Server:
    def __init__(
        self,
    
        host: str = "127.0.0.1",  # Host where the raw TCP/HTTP socket will listen.
        port: int = 10001, # Port where the HTTP server accepts requests.
        num_workers: int = 3,
        max_active_workers: int = 2,
        cache_ttl: int = 10,
        files_dir: str = "files",
    ) -> None:
        # HTTP socket configuration.
        self.host = host
        self.port = port
        self.files_dir = Path(files_dir)

        self.queue = RequestQueue()  # shared queue
        self.num_workers = num_workers
        self.workers: list[threading.Thread] = []  # list of threads created
        self.max_active_workers = max_active_workers  # limit of active workers
        self.worker_slots = threading.Semaphore(max_active_workers)  # controls active workers
        self.cache = ThreadSafeCache(ttl_seconds=cache_ttl)
        self.logger = setup_logger()

        # Socket and acceptor thread used only to receive TCP connections.
        self.server_socket: socket.socket | None = None
        self.accept_thread: threading.Thread | None = None
        # Event used to stop the accept loop and serve_forever loop cleanly.
        self.running = threading.Event()

        # Statistics shared by workers; protected with a lock.
        self.stats_lock = threading.Lock()
        # Unique id assigned to every accepted HTTP connection.
        self.next_request_id = 1
        self.total_requests_received = 0
        self.total_requests_processed = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.cache_waits = 0
        self.computed_results = 0

    # Method to start the server and its worker threads.
    def start(self) -> None:
        # Ensure the file directory exists before requests arrive.
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.running.set()

        self.logger.info(
            "Starting HTTP server on http://%s:%d with %d workers and max_active_workers=%d",
            self.host,
            self.port,
            self.num_workers,
            self.max_active_workers,
        )

        # 1. Create and start worker threads.
        for i in range(self.num_workers):
            worker = threading.Thread(target=self.worker_loop, name=f"worker-{i}")
            self.workers.append(worker)
            worker.start()

        # 2. Create a HTTP server socket that listens for incoming connections.
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        # Timeout lets the accept loop check the running flag periodically.
        self.server_socket.settimeout(1.0)

        # 3. The accept thread only accepts sockets and enqueues them.
        # The HTTP parsing and file processing are done by our own worker pool.
        self.accept_thread = threading.Thread(
            target=self.accept_loop,
            name="http-acceptor",
        )
        self.accept_thread.start()

    # Keep the HTTP server alive until Ctrl+C or stop() is called.
    def serve_forever(self) -> None:
        self.start()
        try:
            while self.running.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        finally:
            self.stop()
            self.print_stats()

    # Receives HTTP connections and puts them into the queue.
    # It doesn't process HTTP requests, workers do that. This separation allows the acceptor to keep accepting new connections while workers are busy processing.
    def accept_loop(self) -> None:
        assert self.server_socket is not None

        while self.running.is_set():
            try:
                # Accept one client connection.
                client_socket, client_address = self.server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            # Avoid blocking forever on clients that never finish sending headers.
            client_socket.settimeout(10.0)

            with self.stats_lock:
                request_id = self.next_request_id
                self.next_request_id += 1
                self.total_requests_received += 1

            request = Request(
                request_id=request_id,  # unique identifier for this request
                client_address=client_address,  # remote IP and port
                client_socket=client_socket,  # socket handled later by a worker
                resource_key="pending",  # filled after parsing the HTTP request
            )

            # simplified logging of accepted connection
            self.logger.info("REQ %s accepted", request.request_id)
            # Put the request into the shared queue for workers to process.
            self.queue.put(request)

    # Each worker thread runs this loop, waiting for requests and processing them.
    def worker_loop(self) -> None:
        while True:
            # Obtain a request from the queue.
            request = self.queue.get()
            # If the queue is closed and empty, return None.
            if request is None:
                break

            # Use a semaphore to limit the number of active workers processing requests concurrently.
            self.worker_slots.acquire()
            try:
                # Process the request.
                self.process_request(request)
            finally:
                # Release the semaphore slot after processing is done.
                self.worker_slots.release()

    def process_request(self, request: Request) -> None:
        try:
            # Parse the HTTP request line
            method, target = self.read_http_request(request.client_socket)
            # Convert the HTTP target path into a safe cache/file key.
            resource_key = self.resource_key_from_target(target)
            request.resource_key = resource_key

            # Log the start of request processing.
            #self.logger.info(
            #    "Processing REQ %s -> %s",
            #    request.request_id,
            #    resource_key,
            #)

            # Only GET is supported because this server reads text files.
            if method != "GET":
                self.send_json(
                    request.client_socket,
                    405,
                    {"error": "Method not allowed. Use GET."},
                    extra_headers={"Allow": "GET"},
                )
                self.mark_processed()
                return

            # Validate the file path before reserving the key in cache.
            file_path = self.resolve_file_path(resource_key)
            # Check the cache for the requested resource. 
            state, data = self.cache.get_or_reserve(resource_key)

            # result exists in cache and is valid
            if state == "hit":
                with self.stats_lock:
                    self.cache_hits += 1
                    self.total_requests_processed += 1

                # Copy cached data so response-only fields do not mutate the cache.
                result = dict(data)
                result["cached"] = True
                result["worker"] = threading.current_thread().name
                self.send_json(request.client_socket, 200, result)
                self.logger.info(
                    "[%s] HIT   %s",
                    threading.current_thread().name,
                    resource_key,
                )                
                return

            # another worker is currently computing the result for this key
            if state == "wait":
                with self.stats_lock:
                    self.cache_waits += 1

                self.logger.info(
                    "[%s] WAIT   %s",
                    threading.current_thread().name,
                    resource_key,
                )
                # Wait until the worker computing this file stores the value.
                value = self.cache.wait_for_value(data)

                with self.stats_lock:
                    self.total_requests_processed += 1

                # Send the computed value after waiting.
                result = dict(value)
                result["cached"] = True
                result["waited"] = True
                result["worker"] = threading.current_thread().name
                self.send_json(request.client_socket, 200, result)
                self.logger.info(
                    "[%s] HIT   %s (after wait)",
                    threading.current_thread().name,
                    resource_key,
                )                
                return

            # state == "compute" (miss): no valid cache entry and no other worker
            # is computing it, so this worker will compute the result.
            entry = data

            with self.stats_lock:
                self.cache_misses += 1
                self.computed_results += 1

            self.logger.info(
                "[%s] MISS  %s -> computing",
                threading.current_thread().name,
                resource_key,
            )
            # Count uppercase letters in the requested text file.
            result = self.count_uppercase_letters(resource_key, file_path)
            # Store the result and wake up any workers waiting for the same file.
            self.cache.store(resource_key, entry, result)

            with self.stats_lock:
                self.total_requests_processed += 1

            # Add response metadata without changing the cached value.
            response = dict(result)
            response["cached"] = False
            response["worker"] = threading.current_thread().name
            self.send_json(request.client_socket, 200, response)

            self.logger.info(
                "[%s] DONE  %s -> uppercase=%s",
                threading.current_thread().name,
                resource_key,
                result["uppercase_letters"],
            )

        except FileNotFoundError:
            # Requested file does not exist inside files_dir.
            self.send_json(
                request.client_socket,
                404,
                {"error": f"File not found: /{request.resource_key}"},
            )
            self.mark_processed()
        except ValueError as exc:
            # Bad HTTP request or unsafe/invalid path.
            self.send_json(request.client_socket, 400, {"error": str(exc)})
            self.mark_processed()
        except Exception as exc:
            # Unexpected server-side error.
            self.logger.error(
                "ERROR request_id=%s resource=%s error=%s",
                request.request_id,
                request.resource_key,
                exc,
            )
            self.send_json(request.client_socket, 500, {"error": "Internal server error"})
            self.mark_processed()
        finally:
            # Every request uses a short-lived HTTP connection.
            request.client_socket.close()

    # Read only the HTTP headers 
    def read_http_request(self, client_socket: socket.socket) -> tuple[str, str]:
        data = b"" 
        while b"\r\n\r\n" not in data: # HTTP headers end with a blank line
            chunk = client_socket.recv(4096) # Read up to 4096 bytes at a time
            if not chunk:
                break
            data += chunk
            # Basic protection against very large headers.
            if len(data) > 8192:
                raise ValueError("HTTP request headers are too large")

        if not data:
            raise ValueError("Empty HTTP request")

        # Parse the request line, which is the first line of the HTTP request.
        request_line = data.decode("iso-8859-1").splitlines()[0]

        # Split the request line into method, target, and HTTP version. Validate the format.
        parts = request_line.split()
        if len(parts) != 3 or not parts[2].startswith("HTTP/"):
            raise ValueError("Malformed HTTP request line")

        method, target, _version = parts
        return method.upper(), target

    # Convert a URL target such as /test.txt into a safe relative file key.
    # Avoid that the client read any file on the system by requesting paths like /../../secret.txt. 
    def resource_key_from_target(self, target: str) -> str:
        # urlparse also handles absolute-form requests from some clients.
        parsed = urlparse(target)
        # Decode escaped characters such as %20.
        path = unquote(parsed.path)
        if path in ("", "/"):
            raise ValueError("Request a file path, for example /test.txt")

        # Remove the leading slash to get a relative path, and prevent directory traversal by rejecting paths with "..".
        resource_key = path.lstrip("/")
        # Reject empty paths and directory traversal.
        if not resource_key or ".." in Path(resource_key).parts:
            raise ValueError("Invalid file path")

        return resource_key

    # Resolve the requested file and guarantee it stays inside files_dir.
    def resolve_file_path(self, resource_key: str) -> Path:
        base_dir = self.files_dir.resolve()
        file_path = (base_dir / resource_key).resolve()

        try:
            file_path.relative_to(base_dir)
        except ValueError as exc:
            raise ValueError("Invalid file path") from exc

        if not file_path.is_file():
            raise FileNotFoundError(resource_key)

        return file_path

    # Count uppercase letters in a text file.
    def count_uppercase_letters(self, resource_key: str, file_path: Path) -> dict[str, int | str]:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        uppercase_count = sum(1 for char in text if char.isupper())

        # Return structured data so the HTTP response and cache use the same result.
        return {
            "file": resource_key,
            "uppercase_letters": uppercase_count,
            "bytes": file_path.stat().st_size,
        }

    # Send a minimal HTTP/1.1 JSON response.
    def send_json(
        self,
        client_socket: socket.socket,
        status_code: int,
        payload: dict,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        # Translate status codes into reason phrases.
        reason = {
            200: "OK",
            400: "Bad Request",
            404: "Not Found",
            405: "Method Not Allowed",
            500: "Internal Server Error",
        }.get(status_code, "OK")

        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Content-Length": str(len(body)),
            "Connection": "close",
        }
        if extra_headers:
            headers.update(extra_headers)

        header_lines = [f"HTTP/1.1 {status_code} {reason}"]
        header_lines.extend(f"{name}: {value}" for name, value in headers.items())
        # HTTP headers are separated from the body by a blank line.
        response = ("\r\n".join(header_lines) + "\r\n\r\n").encode("ascii") + body
        client_socket.sendall(response)

    # Count requests that finished with an error or unsupported method.
    def mark_processed(self) -> None:
        with self.stats_lock:
            self.total_requests_processed += 1

    # Stop acceptor and workers
    def stop(self) -> None:
        if not self.running.is_set():
            return

        self.logger.info("Stopping server")
        # Tell serve_forever and accept_loop to stop.
        self.running.clear()

        if self.server_socket is not None:
            try:
                self.server_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.server_socket.close()

        if self.accept_thread is not None:
            self.accept_thread.join()

        # Closing the queue wakes workers that are waiting in get().
        self.queue.close()
        for worker in self.workers:
            worker.join()

        self.logger.info("All workers stopped")

    # Print final statistics after the server stops.
    def print_stats(self) -> None:
        with self.stats_lock:
            print("\n===== SERVER STATISTICS =====")
            print(f"Total requests received : {self.total_requests_received}")
            print(f"Total requests processed: {self.total_requests_processed}")
            print(f"Cache hits              : {self.cache_hits}")
            print(f"Cache misses            : {self.cache_misses}")
            print(f"Cache waits             : {self.cache_waits}")
            print(f"Computed results        : {self.computed_results}")
            print("=============================\n")
