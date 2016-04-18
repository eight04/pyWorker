#! python3

"""Worker

A threaded worker, implemented with message queue and parent/child pattern.
"""

import queue, threading, traceback, time, inspect, weakref

__version__ = "0.3.0"

class WorkerExit(BaseException):
	"""Raise this error will exit current thread. The user can use
	thread.exit.
	"""
	pass

class Event:
	"""Event"""
	def __init__(self, name, data=None, bubble=False, broadcast=False, target=None):
		self.name = name
		self.data = data
		self.target = target

		self.bubble = bubble
		self.broadcast = broadcast

class Listener:
	"""Event listener"""
	def __init__(self, callback, event_name, target=None, priority=0):
		self.callback = callback
		self.event_name = event_name
		self.target = target
		self.priority = priority

class Worker:
	"""Live message node, integrate with thread"""
	def __init__(self, worker=None, parent=True, daemon=None):
		self.node_name = str(self)
		
		self.children = set()
		self.pending = set()
		
		self.listeners = {}
		self.listener_pool = {}

		self.thread = None
		self.event_que = None
		self.event_cache = None

		self.suspend = False
		
		self.err = None
		self.ret = None
		
		if worker:
			self.worker = worker
			self.node_name = str(worker)
			
		if isinstance(parent, Worker):
			self.parent_node = parent
		elif parent and not worker_pool.is_main():
			self.parent_node = worker_pool.current()
		else:
			self.parent_node = None
			
		if self.parent_node:
			self.parent_node.children.add(self)
		
		self.daemon = daemon
		
		self.callwith_thread = False
		# try to get thread param from worker
		try:
			sig = inspect.signature(self.worker)
		except ValueError:
			pass
		else:
			for name in sig.parameters:
				if name == "thread":
					self.callwith_thread = True
					break

		# listen to builtin event
		@self.listen("STOP_THREAD", priority=-100)
		def _(event):
			"""Stop thread"""
			raise WorkerExit

		@self.listen("PAUSE_THREAD", priority=-100)
		def _(event):
			if not self.suspend and self.thread:
				self.suspend = True
				self.wait_event("RESUME_THREAD", cache=True)
				self.suspend = False
				
		@self.listen("CHILD_THREAD_START", priority=100)
		def _(event):
			self.children.add(event.target)
			
		@self.listen("CHILD_THREAD_END", priority=-100)
		def _(event):
			self.children.remove(event.target)
			
		@self.listen("PENDING")
		def _(event):
			self.pending.add(event.target)
			
		@self.listen("EVENT_REJECT")
		def _(event):
			err_event, err_target = event.data
			if err_event.name == "PENDING":
				self.fire("PENDING_DONE", target=err_target)
			
	def parent(self, parent_node):
		"""Setup parent_node"""
		if self.parent_node:
			self.parent_node.children.remove(self)
		self.parent_node = parent_node
		self.parent_node.children.add(self)
		return self
				
	def fire(self, event, *args, **kwargs):
		"""Dispatch an event"""
		if not isinstance(event, Event):
			event = Event(event, *args, **kwargs)
		self.que_event(event)
		self.transfer_event(event)
		return self

	def que_event(self, event):
		"""Que the event"""
		try:
			self.event_que.put(event)
		except AttributeError as err:
			if event.target:
				event.target.fire("EVENT_REJECT", data=(event, self))

	def transfer_event(self, event):
		"""Bubble or broadcast event"""
		if event.bubble:
			self.parent_fire(event)

		if event.broadcast:
			self.children_fire(event)
			
	def children_fire(self, event):
		"""Fire event on children."""
		for child in self.children.copy():
			child.fire(event)

	def process_event(self, event):
		"""Deliver the event to listeners"""
		if event.name in self.listeners:
			for listener in self.listeners[event.name]:
				if listener.target is None or listener.target is event.target:
					try:
						listener.callback(event)
					except Exception as err:
						print("error occurred in listener: " + self.node_name)
						traceback.print_exc()
						self.fire("LISTENER_ERROR", data=err, target=self, bubble=True)

	def listen(self, event_name, *args, **kwargs):
		"""This is a decorator. Listen to a specific message. It follows the signature of Listener.

		For example:
		
		@self.listen("MESSAGE_NAME")
		def callback(event):
			pass
		"""
		def listen_message(callback):
			"""Decorate callback"""
			listener = Listener(callback, event_name, *args, **kwargs)

			if event_name not in self.listeners:
				self.listeners[event_name] = [listener]
			else:
				i = 0
				for t_listener in self.listeners[event_name]:
					if t_listener.priority < listener.priority:
						break
					i += 1
				self.listeners[event_name].insert(i, listener)
			self.listener_pool[callback] = listener
			return callback
		return listen_message

	def unlisten(self, callback):
		"""Unlisten a callback"""
		listener = self.listener_pool[callback]
		self.listeners[listener.event_name].remove(listener)
		del self.listener_pool[callback]
		
	def is_running(self):
		"""Check if the thread is running"""
		return self.thread is not None

	def is_daemon(self):
		"""Check if the thread is daemon. Daemon can be True, Falase, or None.
		
		When daemon is None, it will try to inherit daemon value from its 
		parent.
		"""
		if self.daemon is not None:
			return self.daemon

		parent = self.parent_node
		if parent:
			return parent.is_daemon()
		return False

	def worker(self):
		"""Default worker. Inifinite loop"""
		self.wait_timeout(-1)
		
	def wait(self, param, *args, **kwargs):
		"""Wait interface. Choose method by type"""
		if isinstance(param, str):
			self.wait_event(param, *args, **kwargs)
		elif isinstance(param, Worker):
			self.wait_thread(param, *args, **kwargs)
		else:
			self.wait_timeout(param, *args, **kwargs)

	def wait_timeout(self, timeout):
		"""Wait for timeout. Process events"""
			
		time_start = time.time()
		time_end = time_start

		while time_end - time_start <= timeout or timeout < 0:
			if not self.event_cache.empty():
				event = self.event_cache.get_nowait()
			else:
				try:
					event = self.event_que.get(timeout=timeout - (time_end - time_start) if timeout > 0 else None)
				except queue.Empty:
					return
				# FIXME: should we make Node.process_event thread safe?
				self.process_event(event)

			time_end = time.time()

	def wait_event(self, name, target=None, cache=False):
		"""Wait for event. Process events and return event data"""

		while not self.event_cache.empty():
			event = self.event_cache.get_nowait()
			if name == event.name:
				if target is None or target == event.target:
					return event.data

		while True:
			event = self.event_que.get()
			# FIXME: should we make Node.process_event thread safe?
			self.process_event(event)

			if event.name == name:
				if target is None or target == event.target:
					return event.data

			if cache:
				self.event_cache.put(event)
				
	def wait_thread(self, thread):
		"""Wait for thread end"""
		thread.fire("PENDING", target=self)
		self.wait_event("PENDING_DONE", target=thread)
		return (thread.err, thread.ret)

	def parent_fire(self, *args, **kwargs):
		"""Fire event to parent. Thread safe."""
		parent = self.parent_node
		if parent:
			self.parent_node.fire(*args, **kwargs)
			
	def wrap_worker(self, *args, **kwargs):
		"""Real target to send to threading library"""
		
		worker_pool.add(self)

		self.parent_fire("CHILD_THREAD_START", target=self)

		# execute target
		self.ret = None
		self.err = None
			# args.insert(self)
		try:
			if self.callwith_thread:
				self.ret = self.worker(*args, self, **kwargs)
			else:
				self.ret = self.worker(*args, **kwargs)
		except WorkerExit:
			self.parent_fire("CHILD_THREAD_STOP", target=self)
		except BaseException as err:
			self.err = err
			print("thread crashed: " + self.node_name)
			traceback.print_exc()
			self.parent_fire("CHILD_THREAD_ERROR", data=err, target=self)
		else:
			self.parent_fire("CHILD_THREAD_DONE", data=self.ret, target=self)
			
		# remove from pool
		worker_pool.remove(self)
		
		# cache the event que
		event_que = self.event_que
		
		# mark thread as end
		self.event_que = None
		self.event_cache = None		
		self.thread = None
		
		# cleanup event que
		while True:
			try:
				event = event_que.get_nowait()
				self.process_event(event)
			except queue.Empty:
				break
			except WorkerExit:
				pass
			except BaseException as err:
				print("Uncaught BaseException during cleanup: " + self.node_name)
				traceback.print_exc()
				
		# tell parent thread end
		self.parent_fire("CHILD_THREAD_END", data=(self.err, self.ret), target=self)
		
		# tell pending thread end
		for thread in self.pending.copy():
			thread.fire("PENDING_DONE", target=self)
			self.pending.remove(thread)
				
		# stop childrens
		for child in self.children.copy():
			if child.is_daemon():
				child.stop()
			else:
				child.stop().join()
			self.children.remove(child)
		
	def start(self, *args, **kwargs):
		"""Start thread. Not thread safe. You shouldn't rapidly call this 
		method"""
		if not self.thread:
			self.thread = threading.Thread(
                target=self.wrap_worker,
				daemon=self.daemon,
				args=args, 
				kwargs=kwargs
			)	
			self.event_que = queue.Queue()
			self.event_cache = queue.Queue()
			self.thread.start()
		return self

	def start_as_main(self, *args, **kwargs):
		"""Overlay on current thread"""
		if not self.thread:
			self.thread = threading.current_thread()
			self.event_que = queue.Queue()
			self.event_cache = queue.Queue()
			self.wrap_worker(*args, **kwargs)
		return self

	def stop(self):
		"""Stop thread"""
		self.fire("STOP_THREAD")
		return self

	def pause(self):
		"""Pause thread"""
		self.fire("PAUSE_THREAD")
		return self

	def resume(self):
		"""Resume thread"""
		self.fire("RESUME_THREAD")
		return self
		
	def join(self):
		"""thread join method. Thread safe"""
		real_thread = self.thread
		if real_thread:
			real_thread.join()
		return self

	@staticmethod
	def exit():
		"""Exit thread"""
		raise WorkerExit

	@staticmethod
	def async(callback, *args, **kwargs):
		"""Create Async"""
		return Async(callback, *args, **kwargs)

	@staticmethod
	def await(async):
		"""Wait async return"""
		return async.get()

	@staticmethod
	def sync(callback, *args, **kwargs):
		"""Sync call"""
		return Async(callback, *args, **kwargs).get()
		
class Async:
	"""Async object"""
	def __init__(self, callback, *args, **kwargs):
		"""Create async thread"""
		if isinstance(callback, Worker):
			self.thread = callback
		else:
			self.thread = Worker(callback, parent=None, daemon=True)
		self.thread.start(*args, **kwargs)

	def get(self):
		"""Wait for thread ending"""
		err, ret = worker_pool.current().wait_thread(self.thread)
		
		if err:
			raise err
		return ret

class RootWorker(Worker):
	"""Root node. Represent main thread"""
	def __init__(self):
		super().__init__()
		self.thread = threading.main_thread()
		self.event_que = queue.Queue()
		self.event_cache = queue.Queue()

	def wait(self, *args, **kwargs):
		try:
			super().wait(*args, **kwargs)
		except WorkerExit:
			self.fire("STOP_THREAD", broadcast=True)

	def wait_event(self, *args, **kwargs):
		try:
			super().wait_event(*args, **kwargs)
		except WorkerExit:
			self.fire("STOP_THREAD", broadcast=True)
			
class Pool:
	"""Worker pool"""
	def __init__(self):
		self.pool = {}
		self.lock = threading.Lock()
		
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

	def remove(self, node):
		"""Remove worker from pool"""
		with self.lock:
			if len(self.pool[node.thread]) == 1:
				del self.pool[node.thread]
			else:
				self.pool[node.thread].pop()
	
	@staticmethod
	def is_main():
		"""Check if the current thread is main thread"""
		return threading.current_thread() is threading.main_thread()
				
class Channel:
	"""Pub, sub channel"""
	def __init__(self):
		self.pool = weakref.WeakSet()
		self.lock = threading.Lock()
		
	def sub(self, thread):
		"""Subscribe to channel"""
		with self.lock:
			self.pool.add(thread)
		
	def pub(self, event, *args, **kwargs):
		"""Publish to channel"""
		with self.lock:
			for thread in self.pool:
				thread.fire(event, *args, **kwargs)
			
	def unsub(self, thread):
		"""Unsubscribe to channel"""
		with self.lock:
			self.pool.remove(thread)

# init worker pool
worker_pool = Pool()

# init RootWorker
worker_pool.add(RootWorker())

# export useful function
current = worker_pool.current
is_main = worker_pool.is_main
