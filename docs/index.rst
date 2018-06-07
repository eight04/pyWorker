.. currentmodule:: worker

pyThreadWorker
==============

A library which can help you create threaded APP. It adds event queue, parent,
children to each threads.

The document would mention "thread" object multiple times, but it actually
refers to :class:`Worker` instead of builtin :class:`threading.Thread`.

Event loop
----------

This library implements event loop for each thread. Each thread has its own
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

1. Events are processed.
2. Listeners get called. *Note: you should avoid re-enter the event loop inside
   a listener*
3. If there is a "STOP_THREAD" event, :class:`WorkerExit` would be raised.
   *Keep this in mind and carefully add "breakpoints" in your application.*
   
Event
-----

Following events are used:

* ``STOP_THREAD``: raises :class:`WorkerExit` to stop the thread.
* ``PAUSE_THREAD``: pause the thread. When a thread is paused,
  it will not leave the event loop after entering, but listeners still get
  called.
* ``RESUME_THREAD``: resume the thread.
* ``CHILD_THREAD_START``: a child thread is started.
* ``CHILD_THREAD_STOP``: a child thread is stopped.
* ``CHILD_THREAD_DONE``: a child thread is finished without error.
* ``CHILD_THREAD_ERROR``: a child thread raises an error.
* ``CHILD_THREAD_END``: a child thread exits.
* ``WAIT_THREAD_PENDING``: some other threads are waiting this thread. When the
  thread is finished, it fires "WAIT_THREAD_PENDING_DONE" event on each waiter.
* ``WAIT_THREAD_PENDING_DONE``: the pending thread is stopped.
* ``EVENT_REJECT``: If ``a`` thread fails to :meth:`Worker.fire` an event on 
  ``b`` thread, ``a`` thread would receive this event (probably ``b`` thread is
  not running).
* ``EXECUTE``: execute a function on targeted thread. This event is used
  by :class:`Later`.
* ``LISTENER_ERROR``: A listener throws. This event bubbles up.
      
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
    
Or, you can listen to "STOP_THREAD" event:

.. code-block:: python

    from worker import create_worker, wait_forever, listen
    
    @create_worker
    def server_thread():
        @listen("STOP_THREAD")
        def _(event):
            server.terminate()
        server = Server()
        server.run()
        wait_forever()
        
    # ... do something ...
    
    server_thread.stop()
    
Or, use contextmanager:

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

Following functions have an optional callback as the first argument. They are
allowed to be used as a decorator. Take :func:`create_worker` for example:

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

.. autofunction:: create_worker

.. autofunction:: async_
        
.. autofunction:: await_

.. autofunction:: later

Besides :func:`sleep`, there are other shortcut functions that would be bound to
the current thread when called, including:

* ``listen``: *note that listeners created by shortcut function would have
  ``persistent=False``.*
* ``later``
* ``unlisten``
* ``update``
* ``exit``
* ``wait``
* ``wait_timeout``
* ``wait_forever``
* ``wait_thread``
* ``wait_event``
* ``wait_until``
* ``parent_fire``
* ``children_fire``
* ``bubble``
* ``broadcast``

With these functions, we can write our code without referencing to
threads:

.. code-block:: python

    from worker import listen, wait_forever, create_worker
    
    def printer_core():
        # curr_thread = current() no need to do this
        @listen("PRINT") # the listener is registered on printer thread
        def _(event):
            print(event.data)
        wait_forever() # printer's event loop
    
    printer = create_worker(printer_core)
    printer.fire("PRINT", "foo")
    printer.fire("PRINT", "bar")
    printer.stop().join()
        
Classes
-------
        
.. autoclass:: Worker
    :members: listen, unlisten, fire, update, start, stop, pause, resume, join,
        is_running, is_daemon, wait, wait_timeout, wait_forever, wait_thread,
        wait_event, wait_until, later
            
.. autoclass:: Async
    :members: get
            
.. autoclass:: Later
    :members: cancel
    
.. autoclass:: Defer
    :members: resolve, reject, get
    
.. autoclass:: Channel
    :members: sub, unsub, pub
    
.. autoclass:: Event

.. autoclass:: Listener
        