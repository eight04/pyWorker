#! python3

import threading
from threading import RLock, Lock, Thread
import traceback, time, weakref
from contextlib import suppress, contextmanager
from collections import deque
from functools import wraps
from typing import Callable
import queue

__version__ = "0.10.0"

SHORTCUTS = (
    "listen", "unlisten", "update", "exit", "later",
    
    "wait", "wait_timeout", "wait_forever", "wait_thread",
    "wait_event", "wait_until",
    
    "parent_fire", "children_fire", "bubble", "broadcast"
)

@contextmanager
def release_lock(lock):
    lock.release()
    try:
        yield
    finally:
        lock.acquire()

class WorkerExit(BaseException):
    """Raise this error to exit the thread."""
    pass

class Event:
    """Event data class."""
    def __init__(self, name, data=None, *, bubble=False, broadcast=False,
            target=None):
        """        
        :param str name: Event name.
        :param data: Event data.
        :param bool bubble: If true then the event would be bubbled up through
            parent.
        :param bool broadcast: If true then the event would be broadcasted
            to all child threads.
        :param Worker target: Event target. If none then set to the thread
            calling :class:`Worker.fire`.
        """
        self.name = name
        self.data = data
        self.target = target
        self.bubble = bubble
        self.broadcast = broadcast

class Listener:
    """Listener data class."""
    def __init__(
        self, callback, event_name, *, target=None, priority=0, once=False,
        permanent=True
    ):
        """
        :arg callable callback: The listener callback.
        :arg str event_name: The event name.
        :arg Worker target: Only match specific :attr:`event.target`.
        :arg int priority: The listener are ordered in priority. The higher is
            called first.
        :arg bool once: If True then remove the listener once the listener is
            called.
        :arg bool permanent: If False then remove the listener once the thread
            is stopped. Listeners created by :func:`listen` shortcut are
            non-permanent listeners.
        """
        self.callback = callback
        self.event_name = event_name
        self.once = once
        self.permanent = permanent
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
        """Register a listener. See :class:`Listener` for argument details.
            
        If ``callback`` is not provided, this method becomes a decorator, so
        you can use it like:
        
        .. code-block:: python

            @thread.listen("EVENT_NAME")
            def handler(event):
                # handle event...
        """
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
        
    def remove_listener(self, listener):
        self.listeners[listener.event_name].remove(listener)
        self.listener_pool[listener.callback].remove(listener)
        if not self.listener_pool[listener.callback]:
            del self.listener_pool[listener.callback]

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
        listeners = self.listeners.get(event.name, ())
        for listener in listeners[:]:
            if listener.target and listener.target is not event.target:
                continue
            try:
                listener.callback(event)
            except Exception as err: # pylint: disable=broad-except
                self.handle_listener_error(err)
            finally:
                if listener.once:
                    self.remove_listener(listener)
                
    def handle_listener_error(self, err):
        print("Error occurred in listener:")
        traceback.print_exc()
        
    def fire(self, event, *args, **kwargs):
        """Put an event to the event queue.
        
        :arg event: If ``event`` is not an instance of :class:`Event`, it would
            be converted into an :class:`Event` object::
            
                event = Event(event, *args, **kwargs)
        """
        if not isinstance(event, Event):
            event = Event(event, *args, **kwargs)
        if not event.target:
            event.target = current()
        self.que_event(event)
        return self
        
    def event_loop(self, timeout=None, stop_on=None): # pylint: disable=inconsistent-return-statements
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
        """Process all events inside the event queue. This allows you to create
        a break point without waiting.
            
        Use this to hook the event loop into other frameworks. For
        example, tkinter::
            
            from tkinter import Tk
            from worker import update
            
            root = Tk()
            
            def worker_update():
                update()
                root.after(100, worker_update)
                
            worker_update()
            root.mainloop()
        """
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
    """The main Worker class."""
    def __init__(self, task=None, parent=None, daemon=None, print_traceback=True):
        """
        :param Callable task: The function to call when the thread starts. If
            this is not provided, use :meth:`Worker.wait_forever` as the
            default.
        :type parent: Worker or bool
        :param parent: The parent thread.

            If parent is None (the default), it uses the current
            thread as the parent, unless the current thread is the main thread.

            If parent is False. The thread is parent-less.

        :param bool daemon: Create a daemon thread. See also :meth:`is_daemon`.
        :param print_traceback: If True, print error traceback when the thread
            is crashed (``task`` raises an error).
        """
        super().__init__()
        
        self.pending = set()

        self.thread = None

        self.err = None
        self.ret = None

        if task:
            self.worker = task
            self.node_name = str(task)
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
        """Start the thread. The arguments are passed into ``task``.
        """
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
        """Stop the thread."""
        self.fire("STOP_THREAD")
        return self

    def pause(self):
        """Pause the thread."""
        self.fire("PAUSE_THREAD")
        return self

    def resume(self):
        """Resume the thread."""
        self.fire("RESUME_THREAD")
        return self

    def join(self):
        """Join the thread.

        :meth:`join` is a little different with :meth:`wait_thread`:
        
        * :meth:`join` uses native :meth:`threading.Thread.join`, it doesn't
          enter the event loop.
        * :meth:`wait_thread` enters the event loop and waits for the
          ``WAIT_THREAD_PENDING_DONE`` event. It also has a return value:
          ``(thread_err, thread_ret)``.
        """
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
        except BaseException as err: # pylint: disable=broad-except
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
            except BaseException: # pylint: disable=broad-except
                print("Error occured in listener cleanup: " + self.node_name)
                traceback.print_exc()
                
        # cleanup non-permanent listeners
        for listeners in list(self.listeners.values()):
            for listener in listeners[:]:
                if not listener.permanent:
                    self.remove_listener(listener)

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
        """Return True if the thread is live."""
        return self.thread is not None

    def is_daemon(self):
        """Return true if the thread is a daemon thread.

        If ``daemon`` flag is not None, return the flag value.

        Otherwise, return :meth:`parent.is_daemon`.

        If there is no parent thread, return False.
        """
        if self.daemon is not None:
            return self.daemon

        with suppress(AttributeError):
            return self.parent.is_daemon()
        return False

    def wait(self, param, *args, **kwargs):
        """A shortcut method of several ``wait_*`` methods.

        The method is chosen according to the type of the first argument.

        * str - :meth:`wait_event`.
        * :class:`Async` - Just do :meth:`Async.get`.
        * :class:`Worker` - :meth:`wait_thread`.
        * callable - :meth:`wait_until`.
        * others - :meth:`wait_timeout`.
        
        All ``wait_*`` methods enter the event loop.
        """
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
        """Wait for timeout.
        
        :arg float timeout: In seconds. The time to wait.
        """
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
        """Wait for specific event.

        :param str name: Event name.
        :param number timeout: In seconds. If provided, return None when time's up.
        :param Worker target: If provided, it must match ``event.target``.
        :return: Event data.
        """
        def stop_on(event):
            return name == event.name and (not target or target == event.target)            
        event = self.event_loop(timeout, stop_on)
        return event and event.data
            
    def wait_until(self, condition, timeout=None):
        """Wait until ``condition(event)`` returns True.
            
        :param callable condition: A callback function, which receives an
            :class:`Event` object and should return ``bool``.
        :param number timeout: In seconds. If provided, return None when time's
            up.
        :return: Event data.
        """
        event = self.event_loop(timeout, stop_on=condition)
        return event and event.data

    def exit(self):
        """Exit current thread."""
        raise WorkerExit
    
    def later(self, callback, *args, timeout=0, **kwargs):
        """Schedule a task on this thread.
        
        :arg callable callback: The task that would be executed.
        
        :arg float timeout: In seconds.  Wait some time before executing the
            task.
        
        :return: If ``timeout`` is used, this method returns a daemon
            :class:`Worker`, that would first ``sleep(timeout)`` before
            executing the task. Otherwise return None.
        
        :rtype: Worker or None
        
        Other arguments are sent to the callback.
        
        The scheduled task would be executed inside the event loop i.e. inside
        the event listener, so you should avoid blocking in the task.
        
        If a :class:`Worker` is returned, you can :meth:`Worker.stop` the worker
        to cancel the task before the task is executed.
        """
        if not timeout:
            self.fire("EXECUTE", (callback, args, kwargs))
            return None
            
        @create_worker(daemon=True)
        def worker():
            sleep(timeout)
            self.fire("EXECUTE", (callback, args, kwargs))
            
        return worker

class Async(Worker):
    """Async class. Create asynchronous (threaded) task."""
    def __init__(self, task):
        """
        :param Callable task: The worker target.

        This class would initiate a parent-less, daemon thread without printing
        traceback.
        """
        super().__init__(task, parent=False, daemon=True, print_traceback=False)

    def get(self):
        """Get the result.
        
        If the task failed, this method raises an error. If the task is not
        completed, enter the event loop.
        """
        with WORKER_POOL.current_worker() as handle:
            handle.children.add(self)
            err, ret = handle.wait_thread(self)
            handle.children.remove(self)
            if err:
                raise err
            return ret
        
class Defer:
    """Defer object. Handy in cross-thread communication. For example, update
    tkinter GUI in the main thread::
    
        from tkinter import *
        from worker import current, update, create_worker, Defer, is_main

        main_thread = current()
        root = Tk()

        def hook():
            root.after(100, hook)
            update()

        @create_worker
        def worker():
            i = 0
            def update_some_gui(on_finished=None):
                print("gui", is_main())
                def remove_button():
                    button.destroy()
                    on_finished("OK")
                button = Button(
                    root,
                    text="Click me to fulfill defer {}".format(i),
                    command=remove_button
                )
                button.pack()
            while True:
                defer = Defer()
                print("worker", is_main())
                main_thread.later(update_some_gui, on_finished=defer.resolve)
                defer.get()
                i += 1

        hook()
        root.mainloop()
        worker.stop()
    """
    def __init__(self):
        self.status = "PENDING"
        self.status_lock = Lock()
        self.pending = set()
        self.result = None
    
    def resolve(self, value):
        """Resolve with ``value``"""
        self.fulfill("RESOLVED", value)
        
    def reject(self, err):
        """Reject with ``err``"""
        self.fulfill("REJECTED", err)
        
    def fulfill(self, status, result):
        with self.status_lock:
            if self.status != "PENDING":
                return
            self.status = status
            self.result = result
            for thread in self.pending:
                thread.fire("DEFER_FULFILL", self)
            
    def get(self):
        """Enter the event loop and wait util the defer is fulfilled.
        
        If the defer is resolved, return the result. If the defer is rejected,
        raise the result.
        """
        with self.status_lock:
            if self.status != "PENDING":
                return self.get_result()

            with WORKER_POOL.current_worker() as worker:
                def is_fulfilled(event):
                    return event.name == "DEFER_FULFILL" and event.data is self
                self.pending.add(worker)
                with release_lock(self.status_lock):
                    worker.wait_until(is_fulfilled)
                return self.get_result()
        
    def get_result(self):
        if self.status == "RESOLVED":
            return self.result
        raise self.result # pylint: disable=raising-bad-type
                
class RootWorker(Worker):
    """Root worker, represents a root thread i.e. the main thread, or threads that are not managed by pyThreadWorker.

    It is similar to :meth:`Worker.start_overlay` but the worker instance is created automatically when 
    ``wait_*`` shortcuts are invoked. The worker instance is dropped when the ``wait_*`` shortcut returns (unless it is the main thread.)

    This makes pyThreadWorker compatible with other threading libraries e.g. asyncio.
    
    RootWorker overwrite some methods so that:
    
    * It catch BaseException during event loop and print traceback.
    * It only cleanups its children when :meth:`RootWorker.exit` is called.
    """
    def __init__(self):
        super().__init__(parent=False)
        self.thread = threading.current_thread()
        self.init()
        
    def event_loop(self, *args, **kwargs): # pylint: disable=arguments-differ
        """Overwrite :meth:`Worker.event_loop` to catch BaseException."""
        try:
            super().event_loop(*args, **kwargs)
        except WorkerExit:
            self.cleanup_children()
            
        except BaseException: # pylint: disable=broad-except
            traceback.print_exc()
            
    def exit(self):
        """Suppress exit. However, it still cleanups its children."""
        self.cleanup_children()
            
class Pool:
    """Worker pool"""
    def __init__(self):
        self.pool = {}
        self.lock = Lock()

    def current(self):
        """Return current worker"""
        with self.lock:
            return self.pool[threading.current_thread()][-1]

    @contextmanager
    def current_worker(self):
        """A context manager that returns a worker.

        If there is no worker on the current thread, a root worker will be created.
        Which will be removed after the context exits.
        """
        thread = threading.current_thread()
        is_temporary = False
        with self.lock:
            if thread in self.pool:
                worker = self.pool[thread][-1]
            else:
                worker = RootWorker()
                self.pool[thread] = [worker]
                is_temporary = True
        try:
            yield worker
        finally:
            if is_temporary:
                self.remove(thread)

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
    """Channel class. Broadcast events to multiple threads."""
    def __init__(self):
        self.pool = weakref.WeakSet()
        self.lock = Lock()

    def sub(self, thread=None):
        """Subscribe ``thread`` to the channel.
        
        :param Worker thread: The subscriber thread. Use current thread if not
            provided.
        """
        if thread is None:
            thread = WORKER_POOL.current()
        with self.lock:
            self.pool.add(thread)

    def unsub(self, thread=None):
        """Unsubscribe to channel.

        :param Worker thread: The subscriber thread. Use current thread if not
            provided.
        """
        if thread is None:
            thread = WORKER_POOL.current()
        with self.lock:
            self.pool.remove(thread)

    def pub(self, *args, **kwargs):
        """Publish an event to the channel. See :class:`Event` for
        the arguments.
        
        Events published to the channel are broadcasted to all subscriber
        threads.
        """
        with self.lock:
            for thread in self.pool:
                thread.fire(*args, **kwargs)

def current():
    """Get current thread.
    
    :rtype: Worker
    """
    return WORKER_POOL.current()

def is_main(thread=None):
    """Check if the thread is the main thread.
        
    :param Worker thread: Use the current thread if not set.
    :rtype: bool
    """
    return WORKER_POOL.is_main(thread)

def sleep(timeout):
    """Use this function to replace :func:`time.sleep`, to enter the event loop.
        
    This function is a shortcut of ``current().wait_timeout(timeout)``.
    
    :param float timeout: time to wait.
    """
    with WORKER_POOL.current_worker() as worker:
        return worker.wait_timeout(float(timeout))
    
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
def async_(callback: Callable, *args, **kwargs) -> Async:
    """Create and start an :class:`Async` task.
        
    ``callback`` will be sent to :class:`Async` and other arguments will be sent to :meth:`Async.start`.
    """
    return Async(callback).start(*args, **kwargs)

@callback_deco
def await_(callback: Callable, *args, **kwargs) -> any:
    """This is just a shortcut of ``async_(...).get()``, which is used to put
    blocking function into a new thread and enter the event loop.
    """
    return async_(callback, *args, **kwargs).get()
    
@callback_deco
def create_worker(
        callback: Callable,
        *args,
        parent: bool | None | Worker = None,
        daemon: bool | None = None,
        print_traceback: bool = True,
        **kwargs) -> Worker:
    """Create and start a :class:`Worker`.
        
    ``callback``, ``parent``, ``daemon``, and ``print_traceback`` are sent to
    :class:`Worker`, other arguments are sent to :meth:`Worker.start`.
    
    This function can be used as a decorator:

    .. code-block:: python

        def my_task():
            ...
        my_thread = create_worker(my_task, daemon=True)
        # my_thread is running
        
        # v.s.
        
        @create_worker(daemon=True)
        def my_thread():
            ...
        # my_thread is running

    :rtype: Worker
    """
    return Worker(callback, parent=parent, daemon=daemon, 
            print_traceback=print_traceback).start(*args, **kwargs)
            
# define shortcuts
def create_shortcut(key):
    if key == "listen":
        def shortcut(*args, **kwargs):
            return getattr(WORKER_POOL.current(), key)(*args, permanent=False, **kwargs)
    elif key.startswith("wait"):
        def shortcut(*args, **kwargs):
            with WORKER_POOL.current_worker() as worker:
                return getattr(worker, key)(*args, **kwargs)
    else:
        def shortcut(*args, **kwargs):
            return getattr(WORKER_POOL.current(), key)(*args, **kwargs)
    shortcut.__doc__ = (
        "A shortcut function of ``current().{key}()``."
    ).format(key=key)
    return shortcut

for key in SHORTCUTS:
    globals()[key] = create_shortcut(key)
