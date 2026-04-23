import threading # This module provides a way to create and manage threads in Python.

#
class RequestQueue:
    # This class implements a thread-safe queue for handling incoming requests. 
    def __init__(self):
        self._queue = [] # This list will hold the requests in the queue.
        self._lock = threading.Lock() # This lock will be used to synchronize access to the queue. (protect the queue)
        self._not_empty = threading.Condition(self._lock) # This condition variable will be used to wait for the queue to become non-empty.
        self._closed = False # This flag indicates whether the queue has been closed. 

    def put(self, request): # This method adds a request to the queue. It acquires the lock, appends the request to the queue, and then notifies any waiting threads that a new request has been added.
        with self._not_empty: 
            self._queue.append(request)
            self._not_empty.notify() # Notify one waiting thread that a new request has been added.

    def get(self): # This method removes and returns a request from the queue. It acquires the lock, checks if the queue is empty and not closed, and waits if necessary.
        with self._not_empty:
            while not self._queue and not self._closed:
                self._not_empty.wait() # Wait until a request is added or the queue is closed.

            if not self._queue and self._closed: # If the queue is empty and closed, return None to indicate that there are no more requests to process.
                return None

            return self._queue.pop(0) # Remove and return the first request in the queue.

    def close(self): # This method closes the queue. 
        with self._not_empty:
            self._closed = True
            self._not_empty.notify_all()