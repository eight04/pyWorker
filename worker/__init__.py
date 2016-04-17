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
	def __init__(self, callback, event_name, target=None):
		self.callback = callback
		self.event_name = event_name
		self.target = target

class Worker:
	"""Live message node, integrate with thread"""
	def __init__(self, worker=None, parent=True, daemon=None, cleanup=None):
		self.node_name = str(self)
		
		self.children = set()
		
		self.listeners = {}
		self.listener_pool = {}

		self.thread = None
		self.event_que = None
		self.event_cache = None

		self.suspend = False
		
		if worker:
			self.worker = worker
			self.node_name = str(worker)
			
		if isinstance(parent, Worker):
			self.parent_node = parent
		elif parent and not worker_pool.is_main():
			self.parent_node = worker_pool.current()
		else:
			self.parent_node = None
		
		self.daemon = daemon
		
		if cleanup:
			self.cleanup = cleanup
					
		self.callwith_thread = False
		# try to get thread param from worker
		try:
			sig = inspect.signature(self.worker)
		except ValueError:
			pass
		else:
			for pam in sig.parameters:
				if pam.name == "thread":
					self.callwith_thread = True
					break

		# listen to builtin event
		@self.listen("STOP_THREAD")
		def _(event):
			"""Stop thread"""
			raise WorkerExit

		@self.listen("PAUSE_THREAD")
		def _(event):
			if not self.suspend:
				self.suspend = True
				self.wait_event("RESUME_THREAD", cache=True)
				self.suspend = False
				
		@self.listen("CHILD_THREAD_START")
		def _(event):
			self.children.add(event.target)
			
		@self.listen("CHILD_THREAD_END")
		def _(event):
			self.children.remove(event.target)
			
	def parent(self, parent_node):
		"""Setup parent_node"""
		self.parent_node = parent_node
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
		if not self.thread:
			return
		try:
			self.event_que.put(event)
		except AttributeError:
			pass

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
				self.listeners[event_name] = []

			self.listeners[event_name].append(listener)
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
		self.wait(-1)

	def wait(self, timeout):
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
		ret = None
		err = None
		if self.callwith_thread:
			args.insert(self)
		try:
			ret = self.worker(*args, **kwargs)
		except WorkerExit:
			self.parent_fire("CHILD_THREAD_STOP", target=self)
		except BaseException as err:
			err = err
			print("thread crashed: " + self.node_name)
			traceback.print_exc()
			self.parent_fire("CHILD_THREAD_ERROR", data=err, target=self)
		else:
			self.parent_fire("CHILD_THREAD_DONE", data=ret, target=self)

		self.parent_fire("CHILD_THREAD_END", target=self)

		# this should prevent child thread from putting event into que
		self.thread = None
		self.event_que = None
		self.event_cache = None		
				
		# stop childrens
		for child in self.children.copy():
			if child.is_daemon():
				child.stop()
			else:
				child.stop().join()
			self.children.remove(child)
		
		worker_pool.remove(self)
		
		self.cleanup(err, ret)
		
	def cleanup(self, err, ret):
		"""Cleanup function called when thread completely stop"""
		pass
		
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
		"""Create async object"""
		self.child = Worker(callback, parent=None, daemon=True, cleanup=self.cleanup)
		self.waiting_thread = None
		self.lock = threading.Lock()

		self.end = False
		self.ret = None
		self.err = None

		self.child.start(*args, **kwargs)

	def cleanup(self, err, ret):
		"""Cleanup get result"""
		with self.lock:
			self.end = True
			self.ret = ret
			self.err = err
			
			if self.waiting_thread:
				self.waiting_thread.fire("ASYNC_DONE", target=self.child)

	def get(self):
		"""Wait for thread ending"""
		with self.lock:
			if self.end:
				if self.err:
					raise self.err
				return self.ret
			self.waiting_thread = worker_pool.current()
			
		# start waiting
		self.waiting_thread.wait_event("ASYNC_DONE", target=self.child)

		if self.err:
			raise self.err
		return self.ret

class RootWorker(Worker):
	"""Root node. Represent main thread"""
	def __init__(self):
		super().__init__()
		self.thread = threading.main_thread()

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
		self.pool = {}
		self.lock = threading.Lock()
		
	def sub(self, name, thread):
		"""Subscribe to name"""
		with self.lock:
			if name not in self.pool:
				self.pool[name] = []
			ref = weakref.ref(thread)
			self.pool[name].append(ref)
		
	def pub(self, name, event, *args, **kwargs):
		"""Publish to name"""
		with self.lock:
			if name not in self.pool:
				return
			for ref in self.pool[name].copy():
				if ref():
					ref().fire(event, *args, **kwargs)
				else:
					self.pool[name].remove(ref)
					if not self.pool[name]:
						del self.pool[name]
			
	def unsub(self, name, thread):
		"""Unsubscribe to name"""
		with self.lock:
			if name not in self.pool:
				return
			ref = weakref.ref(thread)
			self.pool[name].remove(ref)
			if not self.pool[name]:
				del self.pool[name]
				
worker_pool = Pool()
worker_pool.add(RootWorker())

channel = Channel()
		
# export useful function
current = worker_pool.current
is_main = worker_pool.is_main
pub = channel.pub
sub = channel.sub
unsub = channel.unsub
