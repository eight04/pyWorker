pyThreadWorker
==============

A threading library written in python. Help you build threaded app.

This module was originally included in ComicCrawler_.

.. _ComicCrawler: https://github.com/eight04/ComicCrawler

Features
--------

* Pause, resume, stop thread.
* Create child thread.
* Create async tasks.
* Communicate between threads with Message.

Todos
-----

* Add priority to listener

Install
-------

::

	pip install pythreadworker

Usage
-----

Basic

::

	#! python3

	from worker import Worker

	count = None

	def increaser(thread):
		global count
		count = 1
		while True:
			print(count)
			count += 1
			thread.wait(1)

	ic = Worker(increaser)

	while True:
		command = input("input command: ")

		if command == "pause":
			ic.pause()

		if command == "resume":
			ic.resume()

		if command == "stop":
			ic.stop()
			
		if command == "start":
			ic.start()

		if command == "exit":
			ic.stop()
			break

Async task

::

	#! python3

	from worker import Async
	from time import sleep

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

	def work(thread):
		@thread.listen("PRINT")
		def _(event):
			print(event.data)

		thread.wait(-1) # -1 will create infinite loop

	thread = Worker(work).start()
	thread.fire("PRINT", "Hello thread!")
	thread.stop()
	
Subscribe to channel

::

	#! python3

	from worker import Worker, Channel

	channel = Channel()

	def work(thread):
		channel.sub(thread)
		
		@thread.listen("PRINT")
		def _(event):
			print(event.data)

		thread.wait(-1)

	thread = Worker(work).start()
	channel.pub("PRINT", "Hello channel!")
	thread.stop()

Child thread

::

	#! python3

	from worker import Worker
	from time import sleep

	def grand(thread):
		hello = False
		@thread.listen("HELLO")
		def _(event):
			print("grand")
			nonlocal hello
			if not hello:
				hello = True
				thread.fire("HELLO", bubble=True) # message bubbling is happenened in grand thread
		thread.wait(-1)

	def child(thread):
		@thread.listen("HELLO")
		def _(event):
			print("child")
		Worker(grand).start()
		thread.wait(-1)

	def parent(thread):
		@thread.listen("HELLO")
		def _(event):
			print("parent")
		Worker(child).start()
			
		thread.wait(-1)
		
	thread = Worker(parent).start()
	sleep(1) # message broadcasting is happened in main thread, so the child thread might not be created yet.
	thread.fire("HELLO", broadcast=True)
	sleep(1)
	thread.stop()

Notes
-----
* Thread safe operations: http://effbot.org/pyfaq/what-kinds-of-global-value-mutation-are-thread-safe.htm

Changelog
---------
* Version 0.3.0 (Jun 14, 2015)
	- Catch BaseException.

