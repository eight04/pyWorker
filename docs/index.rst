.. currentmodule:: worker

pyThreadWorker
==============

:Version: |version|
:Github: https://github.com/eight04/pyWorker

A library helping you create threaded App. It adds event queue, parent,
children to each thread.

The document would mention "thread" object multiple times, but it actually
refers to :class:`Worker` instead of builtin :class:`threading.Thread`.

.. toctree::
   :maxdepth: 2

   index

Event loop
----------

This library implements an event loop for each thread. Each thread has its own
event queue. With the event loop, we can pause/resume/stop the thread by 
sending specific events to event queue. For example:

.. code-block:: python

    from worker import create_worker, wait_forever
    
    @create_worker
    def worker():
        print("thread created")
        wait_forever()
        
In the previous code:

1. A thread is created
2. The thread prints "thread created"
3. The thread enters the event loop

The event loop does following stuff:

1. Process events.
2. Call listeners.
3. If there is a "STOP_THREAD" event, :class:`WorkerExit` would be raised.
   *Keep this in mind and carefully add "breakpoints" in your application.*
   
Event system
------------

When you stop a thread by calling :meth:`Worker.stop`, the thread wouldn't stop
immediately:

.. code-block:: python

    from worker import create_worker, wait_forever
    
    @create_worker
    def thread():
      wait_forever()

    thread.stop()
    print(thread.is_running()) # true

When ``stop`` is called, a "STOP_THREAD" event is put in worker's event queue,
after the thread processing the event, the thread would exit the event loop by
raising :class:`WorkerExit`.

To wait until the thread exits:

.. code-block:: python

    from worker import create_worker, wait_forever, wait_thread

    @create_worker
    def thread():
      wait_forever()

    thread.stop()
    wait_thread(thread)
    print(thread.is_running()) # false
      
Daemon thread
-------------

A daemon thread is a thread which won't prevent process to exit. This is
dangerous that the daemon thread would be terminated without any cleanup.

In this library, there is no "real" daemon thread. However, we *do* have a
``daemon`` argument when creating threads, but it works in a different way:

1. When a thread is created, it has a ``parent`` attribute pointing to the
   creator thread (the parent thread).
   
2. When the parent thread exits, it would broadcast a "STOP_THREAD" event to
   its children and wait until all child threads are stopped.
   
3. However, if the child thread is marked as ``daemon=True``, the parent thread
   will not wait it. Since the daemon child thread had received the
   "STOP_THREAD" event, it would eventually stop. But the parent thread doesn't
   know when.

Handle WorkerExit
-----------------

If you want to cleanup something:

.. code-block:: python

    from worker import create_worker, wait_forever
    
    @create_worker
    def server_thread():
        server = Server() # some kinds of multiprocess server
        server.run()
        try:
            wait_forever()
        finally:
            server.terminate() # the server would be correctly terminated when
                               # the event loop raises WorkerExit
            
    # ... do something ...
    
    server_thread.stop()
    
It would look better if the cleanup is wrapped in a contextmanager:

.. code-block:: python

    from contextlib import contextmanager
    from worker import create_worker, wait_forever
    
    @contextmanager
    def open_server():
        server = Server()
        server.run()
        try:
            yield server
        finally:
            server.terminate()
            
    @create_worker
    def server_thread():
        with open_server() as server:
            wait_forever()

    # ... do something ...
    
    server_thread.stop()
    
Exceptions
----------

.. autoexception:: WorkerExit

Functions
---------

.. autofunction:: current

.. autofunction:: is_main

.. autofunction:: sleep

.. autofunction:: create_worker

.. autofunction:: async_
        
.. autofunction:: await_

Shortcut functions for the current thread
-----------------------------------------

.. autofunction:: listen

    .. note::
    
        Listeners created by ``listen`` shortcut would have ``permanent=False``,
        so that the listener wouldn't be added multiple time when the thread is
        restarted.
        
.. autofunction:: unlisten
.. autofunction:: later
.. autofunction:: update
.. autofunction:: wait_timeout
.. autofunction:: wait_forever
.. autofunction:: wait_thread
.. autofunction:: wait_event
.. autofunction:: wait_until

With these shortcuts, we can write code without referencing to threads:

.. code-block:: python

    from worker import listen, wait_forever, create_worker

    @create_worker
    def printer():
        # this function runs in a new thread
        @listen("PRINT") # the listener is registered on printer thread
        def _(event):
            print(event.data)
        wait_forever() # printer's event loop

    printer.fire("PRINT", "foo")
    printer.fire("PRINT", "bar")
    printer.stop().join()
        
Classes
-------
        
.. autoclass:: Worker
    :members: listen, unlisten, fire, update, start, stop, pause, resume, join,
        is_running, is_daemon, wait_timeout, wait_forever, wait_thread,
        wait_event, wait_until, later
            
.. autoclass:: Async
    :show-inheritance:
    :members: get
            
.. autoclass:: Defer
    :members: resolve, reject, get
    
.. autoclass:: Channel
    :members: sub, unsub, pub
    
.. autoclass:: Event

.. autoclass:: Listener
        

