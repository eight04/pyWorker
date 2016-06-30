pyThreadWorker
==============

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

Usage
-----

Basic

::

	#! python3

	from worker import Worker, sleep

	count = None

	def increaser():
		global count
		count = 1
		while True:
			print(count)
			count += 1
			sleep(1)

	thread = Worker(increaser)

	while True:
		command = input("input command: ")

		if command == "pause":
			thread.pause()

		if command == "resume":
			thread.resume()

		if command == "stop":
			thread.stop()
			
		if command == "start":
			thread.start()

		if command == "exit":
			thread.stop()
			break

Async task

::

	#! python3

	from worker import Async, sleep

	def long_work(t):
		sleep(t)
		return "Finished in {} second(s)".format(t)

	async = Async(long_work, 5)

	# Do other stuff here...

	print(async.get())

Listen to event

::

	#! python3

	from worker import Worker

	def create_printer():
		thread = Worker()
		
		@thread.listen("PRINT")
		def _(event):
			print(event.data)
			
		return thread.start()

	thread = create_printer()
	thread.fire("PRINT", "Hello thread!")
	thread.stop()
	
Subscribe to channel

::

	#! python3

	from worker import Worker, Channel

	def create_worker():
		thread = Worker()
		@thread.listen("PRINT")
		def _(event):
			print(event.data)
		channel.sub(thread)
		return thread.start()

	channel = Channel()
	thread = create_worker()
	channel.pub("PRINT", "Hello channel!")
	thread.stop()

Child thread and bubble/broadcast

::

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
		
	# broadcast/bubble is happened in main thread. It doesn't gaurantee the execution order of listeners.
	parent.fire("HELLO", broadcast=True)
	sleep(1)
	grand.fire("HELLO", bubble=True)
	sleep(1)

	# stop a thread will cause its children to stop
	parent.stop()

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

