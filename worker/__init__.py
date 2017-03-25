#! python3

"""
worker
======

A library helping you create threaded app. Implemented with event queue
and parent/child pattern.
"""

import threading
from threading import RLock, Lock, Thread
import traceback, time, weakref
from contextlib import suppress
from collections import deque
from functools import wraps
import queue

__version__ = "0.8.0"

SHORTCUTS = (
    "listen", "unlisten", "update", "exit",
    
    "wait", "wait_timeout", "wait_forever", "wait_thread",
    "wait_event", "wait_until",
    
    "parent_fire", "children_fire", "bubble", "broadcast"
)

class WorkerExit(BaseException):
    pass

class Event:
    """Event data class."""
    def __init__(self, name, data=None, *, bubble=False, broadcast=False,
            target=None):
        """Constructor."""
        self.name = name
        self.data = data
        self.target = target

        self.bubble = bubble
        self.broadcast = broadcast

class Listener:
    """Listener data class."""
    def __init__(self, callback, event_name, *, target=None, priority=0):
        self.callback = callback
        self.event_name = event_name
        self.target = target
        self.priority = priority
        
def callback_deco_meth(f):
    """Make method which accept a callback be able to used as a decorator.
    """
    @wraps(f)
    def wrapped(self, *args, **kwargs):
        if args and callable(args[0]):
            return f(self, *args, **kwargs)
        def wrapped(callback):
            return f(self, callback, *args, **kwargs)
        return wrapped
    return wrapped
        
class EventEmitter:
    """Basic event emitter."""
    def __init__(self):
        self.listeners = {}
        self.listener_pool = {}
        self.event_que = None
        self.que_lock = RLock()
        
    def init(self):
        with self.que_lock:
            self.event_que = queue.Queue()
        
    def uninit(self):
        with self.que_lock:
            self.event_que = None
        
    @callback_deco_meth
    def listen(self, callback, *args, **kwargs):
        listener = Listener(callback, *args, **kwargs)

        listeners = self.listeners.setdefault(listener.event_name, [])
        i = 0
        for t_listener in listeners:
            if t_listener.priority < listener.priority:
                break
            i += 1
        listeners.insert(i, listener)

        self.listener_pool.setdefault(callback, []).append(listener)
        return callback

    def unlisten(self, callback):
        """Unlisten a callback"""
        for listener in self.listener_pool[callback]:
            self.listeners[listener.event_name].remove(listener)
        del self.listener_pool[callback]

    def que_event(self, event):
        """Que the event"""
        try:
            with self.que_lock:
                self.event_que.put(event)
        except AttributeError:
            if event.target and event.target is not self:
                event.target.fire("EVENT_REJECT", data=(event, self))

    def process_event(self, event):
        """Deliver the event to listeners."""
        for listener in self.listeners.get(event.name, ()):
            if listener.target and listener.target is not event.target:
                continue
            try:
                listener.callback(event)
            except Exception as err: # pylint: disable=broad-except
                self.handle_listener_error(err)
                
    def handle_listener_error(self, err):
        print("Error occurred in listener:")
        traceback.print_exc()
        
    def fire(self, event, *args, **kwargs):
        if not isinstance(event, Event):
            event = Event(event, *args, **kwargs)
        if not event.target:
            event.target = current()
        self.que_event(event)
        return self
        
    def event_loop(self, timeout=None, stop_on=None):
        """Do event loop."""
        if timeout:
            end_time = time.time() + timeout
        else:
            end_time = None
            
        while timeout is None or timeout > 0:
            try:
                event = self.event_que.get(timeout=timeout)
            except queue.Empty:
                # timeup
                return
                
            self.process_event(event)
            
            if stop_on and stop_on(event):
                return event
        
            if end_time:
                timeout = end_time - time.time()
        
    def update(self):
        while True:
            try:
                event = self.event_que.get_nowait()
            except queue.Empty:
                break
            self.process_event(event)
            
class CachedEventEmitter(EventEmitter):
    """This class adds cache mechanics to EventEmitter, to allow suspended
    emmiter buffing the incoming events.
    """
    def __init__(self):
        super().__init__()
        self.use_cache = False
        self.processed_events = None
        
    def init(self):
        super().init()
        self.processed_events = deque()
        
    def uninit(self):
        super().uninit()
        self.processed_events = None
        
    def process_event(self, event):
        super().process_event(event)
        if self.use_cache:
            self.processed_events.append(event)
        
    def event_loop(self, timeout=None, stop_on=None):
        if timeout:
            end_time = time.time() + timeout
        else:
            end_time = None
            
        while self.processed_events and (timeout is None or timeout > 0):
            event = self.processed_events.popleft()
            
            if stop_on and stop_on(event):
                return event
        
            if end_time:
                timeout = end_time - time.time()
                
        return super().event_loop(timeout, stop_on)
        
class EventTree(CachedEventEmitter):
    """Link multiple EventEmitter with parent/children to create a EventTree.
    """
    def __init__(self):
        super().__init__()
        self.parent = None
        self.children = set()
        
    def handle_listener_error(self, err):
        super().handle_listener_error(err)
        self.fire("LISTENER_ERROR", data=err, bubble=True)
        
    def que_event(self, event):
        super().que_event(event)
        self.transfer_event(event)
        
    def transfer_event(self, event):
        """Bubble or broadcast event"""
        if event.bubble:
            self.parent_fire(event)

        if event.broadcast:
            self.children_fire(event)

    def bubble(self, *args, **kwargs):
        kwargs["bubble"] = True
        self.parent_fire(*args, **kwargs)
        return self

    def broadcast(self, *args, **kwargs):
        kwargs["broadcast"] = True
        self.children_fire(*args, **kwargs)
        return self

    def parent_fire(self, *args, **kwargs):
        kwargs["target"] = self
        with suppress(AttributeError):
            self.parent.fire(*args, **kwargs)

    def children_fire(self, *args, **kwargs):
        kwargs["target"] = self
        for child in self.children.copy():
            child.fire(*args, **kwargs)

class Worker(EventTree):
    """Main Worker class"""
    def __init__(self, worker=None, parent=None, daemon=None, print_traceback=True):
        """Constructor"""
        super().__init__()
        
        self.pending = set()

        self.thread = None

        self.err = None
        self.ret = None

        if worker:
            self.worker = worker
            self.node_name = str(worker)
        else:
            self.worker = self.wait_forever
            self.node_name = str(self)

        if parent is None and not WORKER_POOL.is_main():
            # we don't want root worker become a parent thread, because there
            # is less chance for a root worker to cleanup its children. It is
            # enough to use WORKER_POOL to track all workers.
            parent = WORKER_POOL.current()

        self.parent = parent

        if self.parent:
            self.parent.children.add(self)

        self.daemon = daemon
        self.print_traceback = print_traceback
        self.paused = False
        
        self.register_default_listeners()

    def register_default_listeners(self):
        # listen to builtin event
        @self.listen("STOP_THREAD", priority=-100)
        def _(event):
            raise WorkerExit

        @self.listen("PAUSE_THREAD", priority=-100)
        def _(event):
            if self.paused or not self.thread:
                return
            self.paused = True
            self.use_cache = True
            self.wait_event("RESUME_THREAD")
            self.use_cache = False
            self.paused = False
            
            self.processed_events.pop()
    
        @self.listen("CHILD_THREAD_START", priority=100)
        def _(event):
            self.children.add(event.target)

        @self.listen("CHILD_THREAD_END", priority=-100)
        def _(event):
            self.children.remove(event.target)

        @self.listen("WAIT_THREAD_PENDING")
        def _(event):
            self.pending.add(event.target)

        @self.listen("EVENT_REJECT")
        def _(event):
            err_event, err_target = event.data
            if err_event.name == "WAIT_THREAD_PENDING":
                self.fire("WAIT_THREAD_PENDING_DONE", target=err_target)

        @self.listen("EXECUTE")
        def _(event):
            callback, args, kwargs = event.data
            callback(*args, **kwargs)

    def start(self, *args, **kwargs):
        """Start the thread"""
        if not self.thread:
            self.thread = Thread(
                target=self.wrap_worker,
                # daemon=self.daemon,
                args=args,
                kwargs=kwargs
            )
            self.init()
            self.thread.start()
        return self

    def start_overlay(self, *args, **kwargs):
        """Execute the worker, but overlay on the current thread
        instead of creating a new thread.

        Useful if you want to do some setup and create an event loop on the 
        main thread.
        """
        if not self.thread:
            self.thread = threading.current_thread()
            self.init()
            self.wrap_worker(*args, **kwargs)
        return self

    def stop(self):
        """Stop the thread"""
        self.fire("STOP_THREAD")
        return self

    def pause(self):
        """Pause the thread"""
        self.fire("PAUSE_THREAD")
        return self

    def resume(self):
        """Resume the thread"""
        self.fire("RESUME_THREAD")
        return self

    def join(self):
        with suppress(AttributeError):
            self.thread.join()
        return self
        
    def wrap_worker(self, *args, **kwargs):
        """Real target sent to threading.Thread."""

        # add to pool
        WORKER_POOL.add(self)

        # tell parent start
        self.parent_fire("CHILD_THREAD_START")

        # execute target
        self.ret = None
        self.err = None

        try:
            self.ret = self.worker(*args, **kwargs)
        except WorkerExit:
            self.parent_fire("CHILD_THREAD_STOP")
        except BaseException as err:
            self.err = err
            if self.print_traceback:
                print("Thread crashed: " + self.node_name)
                traceback.print_exc()
            self.parent_fire("CHILD_THREAD_ERROR", data=err)
        else:
            self.parent_fire("CHILD_THREAD_DONE", data=self.ret)

        with self.que_lock:
            # cache some data for later use
            event_que = self.event_que
            native_thread = self.thread

            # mark thread as end
            self.uninit()
            self.thread = None

        # cleanup queue
        while True:
            try:
                event = event_que.get_nowait()
                self.process_event(event)
            except queue.Empty:
                break
            except WorkerExit:
                pass
            except BaseException:
                print("Error occured in listener cleanup: " + self.node_name)
                traceback.print_exc()

        # tell parent thread end
        self.parent_fire("CHILD_THREAD_END", data=(self.err, self.ret))

        # tell pending thread end
        for thread in self.pending.copy():
            thread.fire("WAIT_THREAD_PENDING_DONE")
            self.pending.remove(thread)

        # stop childrens
        self.cleanup_children()

        # remove from pool
        WORKER_POOL.remove(native_thread)

    def cleanup_children(self):
        for child in self.children.copy():
            if child.is_daemon():
                child.stop()
            else:
                child.stop().join()
            self.children.remove(child)
            
    def is_running(self):
        """Check if the thread is running."""
        return self.thread is not None

    def is_daemon(self):
        if self.daemon is not None:
            return self.daemon

        with suppress(AttributeError):
            return self.parent.is_daemon()
        return False

    def wait(self, param, *args, **kwargs):
        if isinstance(param, str):
            return self.wait_event(param, *args, **kwargs)
        if isinstance(param, Async):
            return param.get()
        if isinstance(param, Worker):
            return self.wait_thread(param, *args, **kwargs)
        if callable(param):
            return self.wait_until(param, *args, **kwargs)
        return self.wait_timeout(param)

    def wait_timeout(self, timeout):
        """Wait for timeout"""
        return self.wait_event(None, timeout=timeout)

    def wait_forever(self):
        """Create an infinite event loop."""
        return self.wait_event(None)

    def wait_thread(self, thread):
        """Wait thread to end. Return ``(thread_error, thread_result)``
        tuple.
        """
        thread.fire("WAIT_THREAD_PENDING")
        self.wait_event("WAIT_THREAD_PENDING_DONE", target=thread)
        return (thread.err, thread.ret)

    def wait_event(self, name, timeout=None, target=None):
        def stop_on(event):
            return name == event.name and (not target or target == event.target)
            
        event = self.event_loop(timeout, stop_on)
        if event:
            return event.data
            
    def wait_until(self, condition, timeout=None):
        event = self.event_loop(timeout, stop_on=condition)
        if event:
            return event.data

    def exit(self):
        """Exit current thread."""
        raise WorkerExit
        
    def later(self, callback, timeout, *args, **kwargs):
        return Later(callback, timeout, target=self).start(*args, **kwargs)

class Async(Worker):
    """Async class. Used to create async task."""
    def __init__(self, task):
        """Constructor."""
        super().__init__(task, parent=False, daemon=True, print_traceback=False)

    def get(self):
        handle = current()
        handle.children.add(self)
        err, ret = handle.wait_thread(self)
        handle.children.remove(self)
        if err:
            raise err
        return ret
        
class Later(Worker):
    """Later class. Used to run delayed task."""
    def __init__(self, callback, timeout, target=None):
        if target is True:
            target = current()
            
        def worker(*args, **kwargs):
            self.wait_timeout(timeout)
            if target:
                target.fire("EXECUTE", (callback, args, kwargs))
            else:
                callback(*args, **kwargs)
                
        super().__init__(worker, daemon=True)
        
    def cancel(self):
        """Cancel the later task. It is just an alias to :meth:`Worker.stop`"""
        return self.stop()
        
class RootWorker(Worker):
    """Root worker. Represent main thread.
    
    RootWorker overwrite some methods so that:
    
    * It catch BaseException during event loop and print traceback.
    * It only cleanups its children when :meth:`RootWorker.exit` is called.
    """
    def __init__(self):
        super().__init__(parent=False)
        self.thread = threading.main_thread()
        self.init()
        
    def event_loop(self, *args, **kwargs): # pylint: disable=arguments-differ
        """Overwrite :meth:`Worker.event_loop` to catch BaseException."""
        try:
            super().event_loop(*args, **kwargs)
        except WorkerExit:
            self.cleanup_children()
            
        except BaseException:
            traceback.print_exc()
            
    def exit(self):
        """Suppress exit. However, it still cleanups its children."""
        self.cleanup_children()
        return
            
class Pool:
    """Worker pool"""
    def __init__(self):
        self.pool = {}
        self.lock = Lock()

    def current(self):
        """Return current worker"""
        with self.lock:
            return self.pool[threading.current_thread()][-1]

    def add(self, node):
        """Add worker to pool"""
        with self.lock:
            if node.thread not in self.pool:
                self.pool[node.thread] = []
            self.pool[node.thread].append(node)

    def remove(self, thread):
        """Remove worker from pool"""
        with self.lock:
            if len(self.pool[thread]) == 1:
                del self.pool[thread]
            else:
                self.pool[thread].pop()

    def is_main(self, thread=None):
        """Check if the thread is the main thread.

        thread - the thread to check. Use current thread if not provided.
        """
        if not thread:
            thread = self.current()
        with self.lock:
            return thread is self.pool[threading.main_thread()][-1]

# init worker pool
WORKER_POOL = Pool()

# init RootWorker
WORKER_POOL.add(RootWorker())

class Channel:
    """Channel class."""
    def __init__(self):
        """Constructor."""
        self.pool = weakref.WeakSet()
        self.lock = Lock()

    def sub(self, thread=None):
        if thread is None:
            thread = WORKER_POOL.current()
        with self.lock:
            self.pool.add(thread)

    def unsub(self, thread=None):
        if thread is None:
            thread = WORKER_POOL.current()
        with self.lock:
            self.pool.remove(thread)

    def pub(self, *args, **kwargs):
        """Publish an event to the channel. See :meth:`EventEmitter.fire` for
        the arguments.
        """
        with self.lock:
            for thread in self.pool:
                thread.fire(*args, **kwargs)

def current():
    """Get current thread."""
    return WORKER_POOL.current()

def is_main(thread=None):
    return WORKER_POOL.is_main(thread)

def sleep(timeout):
    """An alias to ``current().wait_timeout()``."""
    return current().wait_timeout(float(timeout))
    
def callback_deco(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if args and callable(args[0]):
            return f(*args, **kwargs)
        def wrapped(callback):
            return f(callback, *args, **kwargs)
        return wrapped
    return wrapped
    
@callback_deco
def async_(callback, *args, **kwargs):
    return Async(callback).start(*args, **kwargs)

@callback_deco
def await_(callback, *args, **kwargs):
    return async_(callback, *args, **kwargs).get()
    
@callback_deco
def later(callback, timeout, *args, target=None, **kwargs):
    """Delay the callback call with timeout seconds."""
    return Later(callback, timeout, target=target).start(*args, **kwargs)

@callback_deco
def create_worker(callback, *args, parent=None, daemon=None,
        print_traceback=True, **kwargs):
    """Create and start a worker."""
    return Worker(callback, parent=parent, daemon=daemon, 
            print_traceback=print_traceback).start(*args, **kwargs)
    
# define shortcuts
def create_shortcut(key):
    def shortcut(*args, **kwargs):
        return getattr(WORKER_POOL.current(), key)(*args, **kwargs)
    shortcut.__doc__ = (
        "A shortcut function to ``current().{key}()``."
    ).format(key=key)
    return shortcut

for key in SHORTCUTS:
    globals()[key] = create_shortcut(key)
