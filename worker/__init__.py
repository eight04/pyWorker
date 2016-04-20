#! python3

"""Worker

A threaded worker, implemented with message queue and parent/child pattern.
"""

import queue, threading, traceback, time, inspect, weakref

__version__ = "0.4.0"

class WorkerExit(BaseException):
	"""Raise this error will exit current thread. The user can use
	thread.exit.
	"""
	pass

class Event:
	"""Event data"""
	def __init__(self, name, data=None, bubble=False, broadcast=False, target=None):
		self.name = name
		self.data = data
		self.target = target

		self.bubble = bubble
		self.broadcast = broadcast

class Listener:
	"""Event listener"""
	def __init__(self, callback, event_name, target=None, priority=0):
		"""Init Listener.
		
		When worker process a event, the listeners will be executed in priority
		order.
		"""
		self.callback = callback
		self.event_name = event_name
		self.target = target
		self.priority = priority

class Worker:
	"""Main Worker class"""
	def __init__(self, worker=None, parent=True, daemon=None):
		"""Init worker.
		
		worker - the threading target. If worker is None, it will use 
		         Worker.worker as target.
		parent - the parent thread. If parent is True (default), it will use 
		         current thread as parent thread.
		daemon - daemon thread. See Worker.is_daemon. If the thread is not a 
		         daemon thread, its parent will do child.join() when stopped.
		"""
		
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
		
		self.async_handle = None
		
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
			
	def fire(self, event, *args, **kwargs):
		"""Dispatch an event. See Event for arguments."""
		if not isinstance(event, Event):
			event = Event(event, *args, **kwargs)
		if not event.target:
			event.target = current()
		self.que_event(event)
		self.transfer_event(event)
		return self
		
	def bubble(self, *args, **kwargs):
		"""Bubble event from parent"""
		kwargs["bubble"] = True
		self.parent_fire(*args, **kwargs)
		return self
		
	def broadcast(self, *args, **kwargs):
		"""Broadcast event from children"""
		kwargs["broadcast"] = True
		self.children_fire(*args, **kwargs)
		return self

	def que_event(self, event):
		"""Que the event"""
		try:
			self.event_que.put(event)
		except AttributeError as err:
			if event.target and event.target is not self:
				event.target.fire("EVENT_REJECT", data=(event, self))

	def transfer_event(self, event):
		"""Bubble or broadcast event"""
		if event.bubble:
			self.parent_fire(event)

		if event.broadcast:
			self.children_fire(event)
			
	def process_event(self, event):
		"""Deliver the event to listeners."""
		if event.name in self.listeners:
			for listener in self.listeners[event.name]:
				if listener.target is None or listener.target is event.target:
					try:
						listener.callback(event)
					except Exception as err:
						print("Error occurred in listener: " + self.node_name)
						traceback.print_exc()
						self.fire("LISTENER_ERROR", data=err, bubble=True)

	def listen(self, event_name, *args, **kwargs):
		"""This is a decorator.
		
		Listen to a specific message. See Listener for arguments."""
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
		"""Check if the thread is daemon.
		
		When Worker.daemon is None, it will try to inherit daemon value from
		its parent.
		"""
		if self.daemon is not None:
			return self.daemon

		parent = self.parent_node
		if parent:
			return parent.is_daemon()
		return False

	def worker(self):
		"""Default worker. Inifinite loop"""
		self.wait_forever()
		
	def wait(self, param, *args, **kwargs):
		"""Wait method.
		
		Choose method by the type of first argument. See Worker.wait_timeout,
		Worker.wait_event, and Worker.wait_thread.
		"""
		if isinstance(param, str):
			return self.wait_event(param, *args, **kwargs)
		if isinstance(param, Worker):
			return self.wait_thread(param, *args, **kwargs)
		if isinstance(param, Async):
			return param.get()
		return self.wait_timeout(param)
		
	def wait_timeout(self, timeout):
		"""Wait for timeout (in seconds)"""
		return self.wait_event(None, timeout=timeout)

	def wait_forever(self):
		"""Wait forever. Event loop."""
		return self.wait_event(None)

	def wait_thread(self, thread):
		"""Wait for thread end"""
		thread.fire("PENDING")
		self.wait_event("PENDING_DONE", target=thread)
		return (thread.err, thread.ret)

	def wait_event(self, name, timeout=None, target=None, cache=False):
		"""Wait for specific event. Return Event.data

		timeout  If provided, return None when time up (in seconds).
		target   If provided, event.target must match target.
		cache    Cache event after processed. Used in PAUSE event.
		"""
		if timeout:
			end_time = time.time() + timeout
		else:
			end_time = None
			
		while True:
			try:
				event = self.event_cache.get_nowait()
			except queue.Empty:
				break
			else:
				if name == event.name:
					if target is None or target == event.target:
						return event.data
				if end_time and time.time() > end_time:
					return

		if end_time:
			timeout = end_time - time.time()
			
		while timeout is None or timeout > 0:
			try:
				event = self.event_que.get(timeout=timeout)
				self.process_event(event)
			except queue.Empty:
				# timeup
				return	
			if event.name == name:
				if not target or target == event.target:
					return event.data
			if cache:
				self.event_cache.put(event)
			if end_time:
				timeout = end_time - time.time()
				
	def parent_fire(self, *args, **kwargs):
		"""Fire event on parent."""
		parent = self.parent_node
		if parent:
			kwargs["target"] = self
			self.parent_node.fire(*args, **kwargs)
			
	def children_fire(self, *args, **kwargs):
		"""Fire event on children."""
		kwargs["target"] = self
		for child in self.children.copy():
			child.fire(*args, **kwargs)

	def wrap_worker(self, *args, **kwargs):
		"""Real target to send to threading.Thread."""
		
		# add to pool
		worker_pool.add(self)

		# tell parent start
		self.parent_fire("CHILD_THREAD_START")

		# execute target
		self.ret = None
		self.err = None

		if self.callwith_thread:
			kwargs["thread"] = self
			
		try:
			self.ret = self.worker(*args, **kwargs)
		except WorkerExit:
			self.parent_fire("CHILD_THREAD_STOP")
		except BaseException as err:
			self.err = err
			print("Thread crashed: " + self.node_name)
			traceback.print_exc()
			self.parent_fire("CHILD_THREAD_ERROR", data=err)
		else:
			self.parent_fire("CHILD_THREAD_DONE", data=self.ret)
			
		# cache some data for later use
		event_que = self.event_que
		native_thread = self.thread
		
		# mark thread as end
		self.event_que = None
		self.event_cache = None		
		self.thread = None
		
		# cleanup queue
		while True:
			try:
				event = event_que.get_nowait()
				self.process_event(event)
			except queue.Empty:
				break
			except WorkerExit:
				pass
			except BaseException:
				print("Error occured in listener cleanup: " + self.node_name)
				traceback.print_exc()
		
		# tell parent thread end
		self.parent_fire("CHILD_THREAD_END", data=(self.err, self.ret))
		
		# tell pending thread end
		for thread in self.pending.copy():
			thread.fire("PENDING_DONE")
			self.pending.remove(thread)
			
		# close async handle
		if self.async_handle:
			self.async_handle.stop()
			self.async_handle = None
				
		# stop childrens
		for child in self.children.copy():
			if child.is_daemon():
				child.stop()
			else:
				child.stop().join()
			self.children.remove(child)
			
		# remove from pool
		worker_pool.remove(native_thread)
		
	def update(self):
		"""Process all event inside event queue"""
		while True:
			try:
				event = self.event_que.get_nowait()
				self.process_event(event)
			except queue.Empty:
				break
			
	def start(self, *args, **kwargs):
		"""Start thread. The arguments will be pass into Worker.worker"""
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

	def start_overlay(self, *args, **kwargs):
		"""Overlay on current thread.
		
		Should only use when you want the worker runs on current thread."""
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
		"""Native thread.join.
		
		thread.join() is a little different with current().wait(thread). Since
		it use native join, it will block until native thread stop. But 
		wait(thread) is not blocking and will return immediately after thread
		exit."""
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
		"""Create Async object"""
		return Async(callback, *args, **kwargs)

	@staticmethod
	def sync(callback, *args, **kwargs):
		"""Sync call"""
		return Async(callback, *args, **kwargs).get()
				
class Async:
	"""Async object"""
	def __init__(self, callback, *args, **kwargs):
		"""Create async thread. callback can be a worker or an callable."""
		if isinstance(callback, Worker):
			self.thread = callback
		else:
			self.thread = Worker(callback, parent=None, daemon=True)
		self.thread.start(*args, **kwargs)

	def get(self):
		"""Wait thread to end"""
		handle = current()
		handle.async_handle = self.thread
		err, ret = handle.wait_thread(self.thread)
		handle.async_handle = None
		if err:
			raise err
		return ret

class RootWorker(Worker):
	"""Root worker. Represent main thread"""
	def __init__(self):
		super().__init__(parent=None)
		self.thread = threading.main_thread()
		self.event_que = queue.Queue()
		self.event_cache = queue.Queue()
		
	def wait_event(self, *args, **kwargs):
		"""Suppress WorkerExit and BaseException"""
		try:
			super().wait_event(*args, **kwargs)
		except WorkerExit:
			self.broadcast("STOP_THREAD")
		except BaseException:
			print("Uncaught BaseException in main thread wait_event")
			traceback.print_exc()
	
	@staticmethod
	def exit():
		"""This method should do nothing with main thread"""
		pass
			
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

	def remove(self, thread):
		"""Remove worker from pool"""
		with self.lock:
			if len(self.pool[thread]) == 1:
				del self.pool[thread]
			else:
				self.pool[thread].pop()
	
	def is_main(self, thread=None):
		"""Check if the thread is main thread"""
		if not thread:
			thread = self.current()
		with self.lock:
			return thread is self.pool[threading.main_thread()][-1]
			
class Channel:
	"""Channel class.
	
	Every events published to the channel will be broadcast to all subscribed
	threads.
	"""
	def __init__(self):
		self.pool = weakref.WeakSet()
		self.lock = threading.Lock()
		
	def sub(self, thread):
		"""Subscribe to channel"""
		with self.lock:
			self.pool.add(thread)
		
	def pub(self, *args, **kwargs):
		"""Publish event to channel. See Worker.fire for arguments."""
		with self.lock:
			for thread in self.pool:
				thread.fire(*args, **kwargs)
			
	def unsub(self, thread):
		"""Unsubscribe to channel"""
		with self.lock:
			self.pool.remove(thread)

def sleep(timeout):
	"""Sleep shortcut"""
	return worker_pool.current().wait(timeout)
			
# init worker pool
worker_pool = Pool()

# init RootWorker
worker_pool.add(RootWorker())

# export useful function
current = worker_pool.current
is_main = worker_pool.is_main
