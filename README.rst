pyThreadWorker
==============

.. image:: https://api.codacy.com/project/badge/Grade/a95224e5ad8c4e52bd8cde3193aab496
   :alt: Codacy Badge
   :target: https://www.codacy.com/app/eight04/pyWorker?utm_source=github.com&utm_medium=referral&utm_content=eight04/pyWorker&utm_campaign=badger

.. image:: https://readthedocs.org/projects/pythreadworker/badge/?version=latest
	:target: http://pythreadworker.readthedocs.io/en/latest/?badge=latest
	:alt: Documentation Status

A threading library written in python. Help you build threaded app.

This module was originally included in ComicCrawler_.

.. _ComicCrawler: https://github.com/eight04/ComicCrawler

Features
--------

* Pause, resume, stop and restart thread.
* Create child thread.
* Create async task.
* Communicate between threads with events.
* Use channel to broadcast event.

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
	from worker import Worker, listen, sleep

	@Worker
	def increaser():
		count = 1
		
		@listen("SET_VALUE")
		def _(event):
			nonlocal count
			count = event.data
			
		while True:
			print(count)
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

	from worker import Async, sleep

	def long_work(t):
		sleep(t)
		return "Finished in {} second(s)".format(t)

	# The async task will be executed in another thread.
	async = Async(long_work, 5)

	# Do other stuff here...

	# Wait the thread to complete and get the result. If the task is already
	# finished, it returns directly with the result.
	print(async.get())

Use Channel to broadcast event:

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
		return printer.start()
		
	foo = create_printer("foo")
	bar = create_printer("bar")

	channel.pub("PRINT", "Hello channel!")

	foo.stop()
	bar.stop()

Child thread and event bubbling/broadcasting:

.. code:: python

	#! python3

	from worker import Worker, sleep

	def create_worker(name, parent):
		thread = Worker(parent=parent)
		
		@thread.listen("HELLO")
		def _(event):
			print(name)
			
		return thread.start()
		
	parent = create_worker("parent", None)
	child = create_worker("child", parent)
	grand = create_worker("grand", child)
		
	# broadcast/bubble is happened in main thread. It doesn't gaurantee the
	# execution order of listeners.
	parent.fire("HELLO", broadcast=True)
	sleep(1)
	grand.fire("HELLO", bubble=True)
	sleep(1)

	# stop a thread would also stop its children
	parent.stop()
	
API reference
-------------
http://pythreadworker.readthedocs.io/en/latest/

Notes
-----

* Thread safe operations: http://effbot.org/pyfaq/what-kinds-of-global-value-mutation-are-thread-safe.htm

Changelog
---------

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

