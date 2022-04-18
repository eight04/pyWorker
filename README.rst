pyThreadWorker
==============

.. image:: https://github.com/eight04/pyWorker/actions/workflows/build.yml/badge.svg
  :target: https://github.com/eight04/pyWorker/actions/workflows/build.yml

.. image:: https://codecov.io/gh/eight04/pyWorker/branch/master/graph/badge.svg
  :target: https://codecov.io/gh/eight04/pyWorker

.. image:: https://readthedocs.org/projects/pythreadworker/badge/?version=stable
  :target: https://pythreadworker.readthedocs.io/en/stable/?badge=stable
  :alt: Documentation Status

A threading library written in python. Help you build threaded app.

This module was originally included in ComicCrawler_.

.. _ComicCrawler: https://github.com/eight04/ComicCrawler

Features
--------

* Pause, resume, stop, and restart a thread.
* Support child threads.
* Easily run asynchronous task across multiple threads.
* Communicate between threads with events.
* Use channel to broadcast events.

Install
-------

::

  pip install pythreadworker

Usage example
-------------

Basic operations and event:

.. code:: python

  #! python3

  # Always use worker.sleep. pyWorker would process event queue during 
  # waiting.
  from worker import create_worker, listen, sleep

  @create_worker
  def increaser():
    count = 1
    
    @listen("SET_VALUE")
    def _(event):
      nonlocal count
      # you don't need a lock to manipulate `count`
      count = event.data
      
    while True:
      print(count)
      # because the listener and the while loop are in the same thread
      count += 1
      sleep(1)

  while True:
    command = input("input command: ")
    
    if command == "start":
      increaser.start()
      
    elif command == "stop":
      increaser.stop()
      
    elif command == "pause":
      increaser.pause()

    elif command == "resume":
      increaser.resume()

    elif command.startswith("set"):
      increaser.fire("SET_VALUE", int(command[4:]))

    elif command == "exit":
      increaser.stop()
      break
      
Async task:

.. code:: python

  #! python3

  from worker import aynsc_, sleep

  def long_work(t):
    sleep(t)
    return "Finished in {} second(s)".format(t)

  # The async task will be executed in another thread.
  pending = async_(long_work, 5)

  # Do other stuff here...

  # Wait the thread to complete and get the result. If the task is already
  # finished, it returns directly with the result.
  print(pending.get())

Use Channel to broadcast events:

.. code:: python

  #! python3

  from worker import Worker, Channel

  channel = Channel()

  def create_printer(name):
    printer = Worker()
    
    @printer.listen("PRINT")
    def _(event):
      print(name, "recieved", event.data)
      
    channel.sub(printer)
    printer.start()
    return printer
    
  foo = create_printer("foo")
  bar = create_printer("bar")

  channel.pub("PRINT", "Hello channel!")

  foo.stop()
  bar.stop()

Child thread and event bubbling/broadcasting:

.. code:: python

  #! python3

  from worker import Worker, sleep

  def create_thread(name, parent):
    thread = Worker(parent=parent)
    
    @thread.listen("HELLO")
    def _(event):
      print(name)
      
    return thread.start()
    
  parent = create_thread("parent", None)
  child = create_thread("child", parent)
  grand = create_thread("grand", child)
    
  # broadcast/bubble is happened in main thread. It doesn't gaurantee the
  # execution order of listeners.
  parent.fire("HELLO", broadcast=True)
  sleep(1)
  grand.fire("HELLO", bubble=True)
  sleep(1)

  # stop a parent thread would also stop its children
  parent.stop()
  
How it works
------------

The module creates a event queue for each thread, including the main thread. When blocking functions are called (``worker.sleep``, ``worker.wait_event``, ``worker.Async.get``, etc), they enter the event loop so the thread can process events, communicate with other threads, or raise an exception during the call.

Which also means that if you don't use functions provided by pyThreadWorker, the module has no chance to affect your existing code. It should be easy to work with other frameworks.
  
API reference
-------------

http://pythreadworker.readthedocs.io/en/latest/

Notes
-----

* Thread safe operations: http://effbot.org/pyfaq/what-kinds-of-global-value-mutation-are-thread-safe.htm

Changelog
---------

* 0.10.0 (Apr 19, 2022)

  - **Change: require python 3.10+.**
  - Change: now calling ``wait_*`` functions would initiate a root worker if there is no worker on the current thread.

* 0.9.0 (Jun 8, 2018)

  - **Change: The signature of `later()` is changed. You should use it to schedule a task on the specific thread.**
  - **Change: The listener registered by `listener()` shortcut would be removed once the thread is stopped.**
  - Add: ``permanent`` and ``once`` arguments to ``Listener``.
  - Add: ``Defer``. A util to handle cross thread communication.

* 0.8.0 (Mar 26, 2017)

  - Add print_traceback option to Worker.
  - Ability to use ``later`` as decorator.
  - Drop __all__ in __init__.py.
  - **function rename: async -> async_, sync -> await_.**
  - **Async now extends Worker and needs start() to run.**
  - **later() now doesn't use current thread as target by default. To use current thread as target, pass target=True.**
  - Various function are able to used as decorator, including ``await_, async_, later``.
  - Drop daemon Thread, use daemon Worker.
  - Add ``Worker.wait_until``.
  - Add ``create_worker``.
  - Refactor.

* 0.7.0 (Feb 26, 2017)

  - Improve docs.
  - Drop ``def target(thread)`` syntax, use ``current()`` to get current thread instead.
  - Use pylint and sphinx.
  - Export `more shortcuts <https://github.com/eight04/pyWorker/blob/4e8d95f64b6925e55a8f688447684343384221b7/worker/__init__.py#L16-L20>`__.

* 0.6.0 (Jul 1, 2016)

  - Add ``thread.later``.

* 0.5.1 (Apr 22, 2016)

  - Use float in sleep function.

* 0.5.0 (Apr 22, 2016)

  - Add sync.

* 0.4.0 (Apr 20, 2016) **breaking change**

  - Interface completely changed
  - Drop ``Message.put, .get``
  - Drop ``UserWorker``
  - Drop ``Worker.create_child``. Use ``parent`` option in constructor instead.
  - Drop ``global_cleanup``
  - Add ``sleep``
  - Add ``current``
  - Add ``Channel``
  - Add ``Listener.priority``
  - Add ``daemon`` option to ``Worker``
  - ``Worker.cleanup`` --> ``Worker.update``
  - ``Worker.message`` --> ``Worker.fire``
  - ``Worker.wait_message`` --> ``Worker.wait_event``
  - ``Worker.message_loop`` --> ``Worker.wait_forever``

* 0.3.0 (Jun 14, 2015)

  - Catch BaseException.

