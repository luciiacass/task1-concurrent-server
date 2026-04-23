import threading
import time

# Cache entries will hold the cached value, the timestamp of when it was computed, a flag indicating if the value is ready, and a condition variable for waiting threads.
class CacheEntry:
    def __init__(self):
        self.value = None
        self.timestamp = None
        self.ready = False
        self.condition = threading.Condition()

# A thread-safe cache implementation with time-to-live (TTL) functionality
class ThreadSafeCache:
    def __init__(self, ttl_seconds=10):
        self._cache = {} # (key -> result)
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds

    def _is_valid(self, entry):
        if entry.timestamp is None:
            return False
        return (time.time() - entry.timestamp) < self._ttl_seconds

    # This method checks the cache for a given key and returns a tuple indicating whether it's a hit, miss, or if the caller has to wait
    def get_or_reserve(self, key):
        with self._lock:
            # If the key is not in the cache, create a new entry 
            if key not in self._cache:
                entry = CacheEntry()
                self._cache[key] = entry
                return "compute", entry

            # If the key is in the cache, check if it's valid. 
            entry = self._cache[key]

            # If the entry is ready and valid, it's a cache hit. 
            if entry.ready and self._is_valid(entry):
                return "hit", entry.value

             # If the entry is ready but not valid, we need to compute a new value. 
             # We replace the old entry with a new one and return "compute".
            if entry.ready and not self._is_valid(entry):
                new_entry = CacheEntry()
                self._cache[key] = new_entry
                return "compute", new_entry

            # If the entry is not ready, another worker is computing the value for this key.
            return "wait", entry

    def wait_for_value(self, entry):
        with entry.condition:
            while not entry.ready:
                entry.condition.wait()
        return entry.value

    def store(self, key, entry, value):
        with self._lock:
            entry.value = value
            entry.timestamp = time.time()
            entry.ready = True

        with entry.condition:
            entry.condition.notify_all()