import threading
import time

from request_queue import RequestQueue
from cache import ThreadSafeCache
from logger_setup import setup_logger

# “a pool of worker threads performs the processing”
# server that:
# - create multiple workers
# - the workers wait for request
# - when the workers receive a request, they process it

class Server:
    def __init__(self, num_workers=3, max_active_workers=2, cache_ttl=10):
        self.queue = RequestQueue() #shared queue  
        self.num_workers = num_workers
        self.workers = [] #list of threads created
        self.max_active_workers = max_active_workers # limit the number of workers that can process requests concurrently
        self.worker_slots = threading.Semaphore(max_active_workers) # semaphore to control the number of active workers processing requests at the same time
        self.cache = ThreadSafeCache(ttl_seconds=cache_ttl)
        self.logger = setup_logger()

        self.stats_lock = threading.Lock()
        self.total_requests_received = 0
        self.total_requests_processed = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.cache_waits = 0
        self.computed_results = 0

    # Method to start the server and its worker threads. 
    def start(self): 
        self.logger.info(
            "Starting server with %d workers and max_active_workers=%d",
            self.num_workers,
            self.max_active_workers
        )

        # Create and start worker threads. 
        for i in range(self.num_workers):
            worker = threading.Thread(
                target=self.worker_loop,
                name=f"worker-{i}"
            )
            self.workers.append(worker)
            worker.start()

    # Method to submit a request to the server. 
    def submit_request(self, request):
        with self.stats_lock:
            self.total_requests_received += 1

        self.logger.info(
            "Received request_id=%s client=%s key=%s",
            request.request_id,
            request.client_id,
            request.resource_key
        )

        # Put the request into the shared queue for workers to process.
        self.queue.put(request)

    # Each worker thread runs this loop, waiting for requests and processing them
    def worker_loop(self):
        while True:
            # Obtain a request from the queue. 
            request = self.queue.get()
            # If the queue is closed and empty, return None.
            if request is None:
                break

            # Use a semaphore to limit the number of active workers processing requests concurrently.
            self.worker_slots.acquire()
            try:
                # Process the request
                self.process_request(request)
            finally:
                # Release the semaphore slot after processing is done, allowing another worker to start processing.
                self.worker_slots.release()

    # The core logic for processing a request, including cache handling and statistics updates
    def process_request(self, request):

        try:
            # Log the start of request processing
            self.logger.info(
                "START request_id=%s client=%s key=%s",
                request.request_id,
                request.client_id,
                request.resource_key
            )

            # Check the cache for the requested resource. The cache returns a state ("hit", "wait", or "miss") and associated data.
            state, data = self.cache.get_or_reserve(request.resource_key)

            if state == "hit": #result exists in cache and is valid
                with self.stats_lock:
                    self.cache_hits += 1
                    self.total_requests_processed += 1

                self.logger.info(
                    "cache HIT key=%s -> %s",
                    request.resource_key,
                    data
                )
                return

            if state == "wait": # another worker is currently computing the result for this key
                with self.stats_lock:
                    self.cache_waits += 1

                self.logger.info(
                    "WAITING for key=%s",
                    request.resource_key
                )

                value = self.cache.wait_for_value(data)

                with self.stats_lock:
                    self.total_requests_processed += 1

                self.logger.info(
                    "cache after WAIT key=%s -> %s",
                    request.resource_key,
                    value
                )
                return

            # state == "compute" (miss): no valid cache entry and no other worker is computing it, so this worker will compute the result
            entry = data

            with self.stats_lock:
                self.cache_misses += 1
                self.computed_results += 1

            self.logger.info(
                "cache MISS key=%s",
                request.resource_key
            )

            time.sleep(2)

            result = f"computed_result_for_{request.resource_key}"

            self.cache.store(request.resource_key, entry, result)

            with self.stats_lock:
                self.total_requests_processed += 1

            self.logger.info(
                "END request_id=%s client=%s key=%s result=%s",
                request.request_id,
                request.client_id,
                request.resource_key,
                result
            )

        except Exception as e:
                self.logger.error(
                "ERROR processing request_id=%s client=%s key=%s error=%s",
                request.request_id,
                request.client_id,
                request.resource_key,
                str(e)
        )

    def stop(self):
        self.logger.info("Stopping server")
        self.queue.close()
        for worker in self.workers:
            worker.join()
        self.logger.info("All workers stopped")

    def print_stats(self):
        with self.stats_lock:
            print("\n===== SERVER STATISTICS =====")
            print(f"Total requests received : {self.total_requests_received}")
            print(f"Total requests processed: {self.total_requests_processed}")
            print(f"Cache hits             : {self.cache_hits}")
            print(f"Cache misses           : {self.cache_misses}")
            print(f"Cache waits            : {self.cache_waits}")
            print(f"Computed results       : {self.computed_results}")
            print("=============================\n")