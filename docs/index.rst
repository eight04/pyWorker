.. automodule:: worker

    The document would mention "thread" object multiple times, but it actually leads
    to :class:`Worker` instead of builtin :class:`threading.Thread`.

    Note for events
    ---------------

    Some event names are already taken by this module, including:

    * ``STOP_THREAD`` - let current thread to stop.
    * ``PAUSE_THREAD`` - let current thread to pause.
    * ``RESUME_THREAD`` - let current thread to resume.
    * ``CHILD_THREAD_START`` - a child thread has started.
    * ``CHILD_THREAD_STOP`` - a child thread has been stopped.
    * ``CHILD_THREAD_DONE`` - a child thread finished.
    * ``CHILD_THREAD_ERROR`` - a child thread failed to finish.
    * ``CHILD_THREAD_END`` - a child thread ended.

    * ``WAIT_THREAD_PENDING`` - some other thread want to wait current
      thread to end.

    * ``WAIT_THREAD_PENDING_DONE`` - the thread current thread waiting
      has ended.

    * ``EVENT_REJECT`` - failed to fire an event. Maybe the thread recieving
      the event is not running.

    * ``EXECUTE`` - let current thread execute a callback.

    * ``LISTENER_ERROR`` - Uncaught error while processing listener. This
      event bubbles up.
      
    Note for daemon threads
    -----------------------

    A daemon thread is a thread which won't stop process to exit. This is
    considered dangerous and worker module tries to avoid it.

    However, there is a ``daemon`` flag for :class:`Worker`. A demon worker won't
    stop its parent to exit, which means that when a worker is going to exit, it
    will wait until all non-daemon children exit.

    API Reference
    -------------

    Exceptions
    ~~~~~~~~~~

    .. autoexception:: WorkerExit

        Raise this error to exit current thread.
        
    Functions
    ~~~~~~~~~

    .. function:: current()

        Return current thread.
        
        :rtype: Worker
        
    .. function:: is_main(thread=None)

        Check if the thread is the main thread.
        
        :param Worker thread: Use current thread if not set.
        :rtype: bool
        
    .. function:: sleep(timeout)

        Use this function to replace :func:`time.sleep`, to enter an event loop.
        
        This function is an shortcut to ``current().wait_timeout()``.
        
    Following functions have an optional callback as the first argument. They are allowed to be used as a decorator::

        func(callback, *args, **kwargs)
        
        # which could be converted to:
        
        @func(*args, **kwargs)
        def callback():
            pass
            
        
        func(callback)
        
        # which could be converted to
        
        @func
        def callback():
            pass
            
    .. function:: create_worker([callback, ]*args, parent=None, daemon=None, print_traceback=True, **kwargs)

        Create and start a :class:`Worker`.
        
        ``callback``, ``parent``, ``daemon``, and ``print_traceback`` are sent to :class:`Worker`, other arguments are sent to :meth:`Worker.start`.
        
        :rtype: Worker
        
    .. function:: async_([callback, ]*args, **kwargs)

        Create and start an :class:`Async` task.
        
        :param callback: The task sent to :class:`Async`.
        :rtype: Async
        
        Other arguments are sent to :meth:`Async.start`.
        
    .. function:: await_([callback, ]*args, **kwargs)

        Execute the callback in an async thread and wait for return.
        
        It is just a shortcut to ``async_(...).get()``, which is used to put
        blocking task into a thread and enter an event loop.
        
    .. function:: later([callback, ]timeout, *args, target=None, **kwargs)

        Create and start a :class:`Later` task.
        
        ``callback``, ``timeout``, and ``target`` are sent to :class:`Later`, and the other arguments are sent to :meth:`Later.start`.
        
        :rtype: Later
        
    Besides :func:`sleep`, there are more shortcut functions working with current thread. Include:

    * listen
    * unlisten
    * update
    * exit
    * wait
    * wait_timeout
    * wait_forever
    * wait_thread
    * wait_event
    * wait_until
    * parent_fire
    * children_fire
    * bubble
    * broadcast

    With these functions, we can write something like::

        from worker import listen, wait_forever, create_worker
        
        @create_worker
        def printer():
            @listen("PRINT") # the callback is registered on printer thread
            def _(event):
                print(event.data)
            wait_forever() # printer's event loop
            
        printer.fire("PRINT", "foo")
        printer.fire("PRINT", "bar")
        printer.stop().join()
        
    Without using explicit :class:`Worker` object.
        
    Classes
    ~~~~~~~
        
    .. class:: Worker(worker=None, parent=None, daemon=None, print_traceback=True)

        The main Worker class, wrapping :class:`threading.Thread`.
        
        :param Callable worker: The function to call when the thread starts. If
            this is not provided, use :meth:`Worker.wait_forever` as the
            default worker.

        :type parent: Worker or False
        :param parent: The parent thread.

            If parent is None (the default), it will use current
            thread as the parent, unless current thread is the main thread.

            If parent is False. The thread is parent-less.

        :param bool daemon: Make thread become a "daemon worker", see also
            :meth:`is_daemon`.
                       
        :param print_traceback: If True, print error traceback when the thread
            crashed.
            
        .. method:: listen([callback,] event_name, *, target=None, priority=0)
        
            Register a callback, listening to specific event.
            
            :param callable callback: The callback function, which would recieve
                an :class:`Event` object.

            :param str event_name: Match :attr:`Event.name`.

            :param Worker target: Optional target. If target is specified, the
                listener would only match those event having the same target.

            :param int priority: When processing events, the listeners would
                be executed in priority order, highest first.
                
            If callback is not provided, this method becomes a decorator::

                @listen("EVENT_NAME")
                def handler(event):
                    # handle event...
                    
        .. method:: unlisten(callback)
        
            Unregister the callback.
            
        .. method:: fire(event_name, data=None, *, bubble=False, broadcast=False, target=None)
        
            Dispatch an event to this emitter.
        
            :param str name: Event name.
            :param data: Event data.
            :param bool bubble: Set to true to bubble through parent thread.
            :param bool broadcast: Set to true to broadcast through child threads.
            
            :param Worker target: An optional target, usually point to the emitter 
                of the event.
                
            When en event is fired, it is not directly sent to listeners but put
            into the event queue. Subclasses should decide when to process those
            events.
            
        .. method:: update()
        
            Process all events inside the event queue.
            
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
                
        .. method:: bubble(event_name, data=None, *, broadcast=False, target=None)
        
            Bubble event through parent. A shortcut to :meth:`parent_fire`, with ``bubble=True``.
            
        .. method:: broadcast(event_name, data=None, *, bubble=False, target=None)
        
            Broadcast event through children. A shortcut to :meth:`children_fire`, with ``broadcast=True``.
            
        .. method:: parent_fire(event_name, data=None, *, bubble=False, broadcast=False, target=None)
        
            Dispatch event on parent.
            
        .. method:: children_fire(event_name, data=None, *, bubble=False, broadcast=False, target=None)
        
            Dispatch event on children.

        Following section contains thread-related methods:
            
        .. method:: start(*args, **kwargs)

            Start the thread. The arguments are passed into the ``worker`` target.
            
        .. method:: stop()
            
            Stop the thread.
            
        .. method:: paus()
        
            Pause the thread.
            
        .. method:: resume()
        
            Resume from pause.
            
        .. method:: join()
        
            Wait thread to exit.

            :meth:`join` is a little different than :meth:`wait_thread`.

            :meth:`join` uses native :meth:`threading.Thread.join`, it blocks
            current thread until the worker is stopped.

            :meth:`wait_thread` enters an event loop and waits for an ``WAIT_THREAD_PENDING_DONE`` event. It also has a return value: ``(thread_err, thread_ret)``.
            
        .. method:: cleanup_children()
            
            Stop all children. This method is called when exiting the current
            thread, to make sure all non-daemon children are stopped.
            
        .. method:: is_running()
        
            Return True if the worker is running.
            
        .. method:: is_daemon()
        
            Check whether the worker is daemon.

            If :attr:`self.daemon` flag is not None, return flag value.

            Otherwise, return :meth:`parent.is_daemon`.

            If there is no parent thread, return False.
            
        Calling following ``wait_*`` methods would enter an event loop:
        
        .. method:: wait(param, *args, **kwargs)
        
            A shortcut method to several ``wait_*`` methods.

            The method is chosen according to the type of the first argument.

            * str - :meth:`wait_event`.
            * :class:`Async` - Just do :meth:`Async.get`.
            * :class:`Worker` - :meth:`wait_thread`.
            * callable - :meth:`wait_until`.
            * others - :meth:`wait_timeout`.
            
        .. method:: wait_timeout(timeout)
        
            Wait for timeout.

            :arg number timeout: In seconds, the time to wait.
            
        .. method:: wait_forever()
        
            Create an infinite event loop.
            
        .. method:: wait_thread(thread)
        
            Wait thread to end.
            
            :arg Worker thread: The thread to wait.
            :return: A ``(error, result)`` tuple.
            
        .. method:: wait_event(name, timeout=None, target=None)
        
            Wait for specific event.

            :param str name: Event name.
            :param number timeout: In seconds. If provided, return None when time's up.
            :param Worker target: If provided, it must match ``event.target``.
            :return: Event data.
            
        .. method:: wait_until(condition, timeout=None)
        
            Wait until ``condition(event)`` returns True.
            
            :param callable condition: A callback function, which receives an Event object and should return boolean.
            :param number timeout: In seconds. If provided, return None when time's
                up.
            :return: Event data.
            
        .. method:: exit()
        
            Exit current thread.
            
        .. method:: later(callback, timeout, *args, **kwargs)
        
            Call :func:`later` with ``target=self``.

    .. class:: Async(task)

        Extends :class:`Worker`, to create async task.
        
        :param Callable task: The worker target. This class would initiate a parent-less, daemon thread without printing traceback.
        
        .. method:: get()
            
            Get the result.
            
    .. class:: Later(callback, timeout, target=None)

        Extends :class:`Worker`, to create delayed task.
        
        :param callback: A callback function to execute after timeout.
            
        :param number timeout: In seconds, the delay before executing the
            callback.
        
        :param Worker target: If set, the callback would be sent to the target 
            thread and let target thread execute the callback. 
            
            If ``target=True``, use current thread as target.
            
            If ``target=None`` (default), just call the callback in the Later
            thread.
            
        .. method:: cancel()
        
            Cancel the task.
            
    .. class:: Channel()

        Channel class. Used to broadcase events to multiple threads.
        
        .. method:: sub(thread=None)

            Subscribe to channel.

            :param Worker thread: The subscriber thread. Use current thread if not
                provided.
                
        .. method:: unsub(thread=None)
        
            Unsubscribe to channel.

            :param Worker thread: The subscriber thread. Use current thread if not
                provided.
                
        .. method:: pub(event_name, data=None, *, bubble=False, broadcast=False, target=None)
        
            Publish an event to the channel.
            
            Events published to the channel are broadcasted to all subscriber threads.
            
    .. autoclass:: Event
        
        Those arguments are set as attributes::
        
            print(event.name, event.data)
        