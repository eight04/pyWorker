#! python3

"""Worker

A threaded worker, implemented with message queue and parent/child pattern.
"""

__version__ = "0.3.0"

import queue, threading, traceback, time, atexit

class WorkerExit(BaseException): pass

class Event:
	"""Event"""
	def __init__(self, name, data=None, bubble=False, broadcast=False, target=None):
		self.name = name
		self.data = data
		self.target = target

		self.bubble = bubble
		self.broadcast = broadcast

class Listener:
	def __init__(self, callback, event_name, target=None):
		self.callback = callback
		self.event_name = event_name
		self.target = target

class Node:
	"""Message node"""
	def __init__(self):
		self.listeners = None
		self.parent_node = None
		self.children = None
		self.node_name = str(self)

		self.listener_pool = None

	def fire(self, event, *args, **kwargs):
		if not isinstance(event, Event):
			event = Event(event, *args, **kwargs)
		self.process_event(event)
		self.transfer_event(event)

	def process_event(self, event):
		if event.name in self.listeners:
			for listener in self.listeners[event.name]:
				if listener.target is None or listener.target is event.target:
					try:
						listener.callback(event)
					except Exception as err:
						print("error occurred in listener: " + self.node_name)
						traceback.print_exc()
						self.fire("LISTENER_ERROR", data=err, target=self, bubble=True)

	def transfer_event(self, event):
		if event.bubble and self.parent_node:
			self.parent_node.fire(event)

		if event.broadcast and self.children:
			for child in self.children:
				child.fire(event)

	def add_child(self, node):
		if not self.children:
			self.children = set()
		self.children.add(node)
		node.parent_node = self
		return node

	def remove_child(self, node):
		self.children.remove(node)
		node.parent_node = None
		return node

	def listen(self, event_name, *args, **kwargs):
		"""This is a decorator. Listen to a specific message.

		The callback should look like `callback(Event)`
		"""
		def listen_message(callback):
			"""Decorate callback"""
			listener = Listener(callback, event_name, *args, **kwargs)

			if not self.listeners:
				self.listeners = {}

			if not self.listener_pool:
				self.listener_pool = {}

			if event_name not in self.listeners:
				self.listeners[event_name] = []

			self.listeners[event_name].append(listener)
			self.listener_pool[callback] = listener
			return callback
		return listen_message

	def unlisten(self, callback):
		listener = self.listener_pool[callback]
		self.listeners[listener.event_name].remove(listener)
		del self.listener_pool[callback]

class LiveNode(Node):
	"""Live message node, integrate with thread"""
	def __init__(self, worker=None, daemon=None, self_destroy=False):
		super().__init__()

		if worker:
			self.worker = worker
			self.node_name = str(worker)
		self.daemon = daemon
		self.self_destroy = self_destroy

		self.reset()
		self.regist_listener()

	def regist_listener(self):
		@self.listen("STOP_THREAD")
		def _(event):
			raise WorkerExit

		@self.listen("PAUSE_THREAD")
		def _(event):
			if not self.suspend:
				self.suspend = True
				self.wait_event("RESUME_THREAD", cache=True)
				self.suspend = False

	def process_event(self, event):
		if self.is_running():
			self.que_event(event)

	def que_event(self, event):
		if not self.event_que:
			self.event_que = queue.Queue()
		self.event_que.put(event)

	def is_running(self):
		return self.thread is not None

	def is_daemon(self):
		if self.daemon is not None:
			return self.daemon

		parent = self.parent_node
		while parent:
			if isinstance(parent, LiveNode):
				return parent.is_daemon()
			parent = parent.parent_node
		return False

	def worker(self):
		self.wait(-1)

	def wait(self, timeout):
		if not self.event_que:
			self.event_que = queue.Queue()
		if not self.event_cache:
			self.event_cache = queue.Queue()

		ts = time.time()
		te = ts

		while te - ts <= timeout or timeout < 0:
			if not self.event_cache.empty():
				event = self.event_cache.get_nowait()
			else:
				try:
					event = self.event_que.get(timeout=timeout - (te - ts) if timeout > 0 else None)
				except queue.Empty:
					return
				super().process_event(event)

			te = time.time()

	def wait_event(self, name, target=None, cache=False):
		if not self.event_que:
			self.event_que = queue.Queue()
		if not self.event_cache:
			self.event_cache = queue.Queue()

		while not self.event_cache.empty():
			event = self.message_cache.get_nowait()
			if name == event.name:
				if target is None or target == event.target:
					return event.data

		while True:
			event = self.event_que.get()
			super().process_event(event)

			if event.name == name:
				if target is None or target == event.target:
					return event.data

			if cache:
				self.event_cache.put(event)

	def parent_fire(self, *args, **kwargs):
		if self.parent_node:
			self.parent_node.fire(*args, **kwargs)

	def thread_target(self, *args, **kwargs):
		pool_add(self)

		self.parent_fire("CHILD_THREAD_START", target=self)

		# execute target
		ret = None
		try:
			ret = self.worker(*args, **kwargs)
		except WorkerExit:
			self.parent_fire("CHILD_THREAD_STOP", target=self)
		except BaseException as err:
			print("thread crashed: " + self.node_name)
			traceback.print_exc()
			self.parent_fire("CHILD_THREAD_ERROR", data=err, target=self)
		else:
			self.parent_fire("CHILD_THREAD_DONE", data=ret, target=self)

		self.parent_fire("CHILD_THREAD_END", target=self)

		pool_remove(self)

		if self.self_destroy and self.parent_node:
			self.parent_node.remove_child(self)

		stop_node_children(self)

		self.reset()

	def reset(self):
		self.thread = None
		self.event_que = None
		self.event_cache = None

		self.suspend = False

	def start(self, *args, **kwargs):
		"""Start thread"""
		if not self.thread:
			self.thread = threading.Thread(target=self.thread_target, daemon=self.daemon, args=args, kwargs=kwargs)
			self.thread.start()
		return self

	def start_as_main(self, *args, **kwargs):
		if not self.thread:
			self.thread = threading.current_thread()
			self.thread_target(*args, **kwargs)
		return self

	def stop(self):
		"""Stop thread"""
		self.fire("STOP_THREAD")
		return self

	def pause(self):
		"""Pause thread"""
		if not self.suspend:
			self.fire("PAUSE_THREAD")
		return self

	def resume(self):
		"""Resume thread"""
		self.fire("RESUME_THREAD")
		return self

	def join(self):
		"""thread join method."""
		if self.thread:
			self.thread.join()
		return self

	def async(self, callback, *args, **kwargs):
		return Async(callback, *args, **kwargs)

	def await(self, async):
		"""Wait async return"""
		return async.get()

	def sync(self, callback, *args, **kwargs):
		"""Sync call"""
		async = self.async(callback, *args, **kwargs)
		return self.await(async)

class Async:
	"""Async object"""

	def __init__(self, callback, *args, **kwargs):
		"""Create async object"""
		self.thread = current_thread()
		self.child = LiveNode(callback, self_destroy=True, daemon=True)

		self.end = False
		self.ret = None
		self.err = None

		self.thread.listen("CHILD_THREAD_END", target=self.child)(self.end_callback)
		self.thread.listen("CHILD_THREAD_DONE", target=self.child)(self.done_callback)
		self.thread.listen("CHILD_THREAD_ERROR", target=self.child)(self.error_callback)

		self.thread.add_child(self.child)
		self.child.start(*args, **kwargs)

	def end_callback(self, event):
		self.end = True
		self.cleanup()

	def done_callback(self, event):
		self.ret = event.data

	def error_callback(self, event):
		self.err = event.data

	def cleanup(self):
		self.thread.unlisten(self.error_callback)
		self.thread.unlisten(self.done_callback)
		self.thread.unlisten(self.end_callback)

	def get(self):
		"""Wait for thread ending"""
		if not self.end:
			self.thread.wait_event("CHILD_THREAD_END", target=self.child)

		if self.err:
			raise self.err

		return self.ret


class RootNode(LiveNode):
	def __init__(self):
		super().__init__()
		self.thread = threading.main_thread()

	def wait(self, *args, **kwargs):
		try:
			super().wait(*args, **kwargs)
		except WorkerExit:
			self.fire("STOP_THREAD", broadcast=True)
			self.reset()

	def wait_event(self, *args, **kwargs):
		try:
			super().wait_event(*args, **kwargs)
		except WorkerExit:
			self.fire("STOP_THREAD", broadcast=True)
			self.reset()

thread_pool = {}

def current_thread():
	return thread_pool[threading.current_thread()][-1]

def pool_add(node):
	if node.thread not in thread_pool:
		thread_pool[node.thread] = []
	thread_pool[node.thread].append(node)

def pool_remove(node):
	if len(thread_pool[node.thread]) == 1:
		del thread_pool[node.thread]
	else:
		thread_pool[node.thread].pop()

pool_add(RootNode())

def stop_node_children(node):
	if not node.children:
		return

	for child in node.children:
		if not isinstance(child, LiveNode):
			stop_node_children(child)
		elif child.is_daemon():
			child.stop()
		else:
			child.stop().join()
