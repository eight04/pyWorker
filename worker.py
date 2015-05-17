#! python3

"""Worker

A threaded worker, implemented with message queue and parent/child pattern.
"""

import queue, threading, traceback, time, inspect, atexit

class WorkerExit(BaseException): pass

class Message:
	"""Message object"""
	
	def __init__(self, message, param, sender, flag):
		"""Create message object"""
		self.message = message
		self.param = param
		self.sender = sender
		self.flag = flag
		self.que = queue.Queue()
		
	def get(self):
		"""Wait for message being processed"""
		return self.que.get()
		
	def put(self, value):
		"""Put returned value"""
		self.que.put(value)
		
class Async:
	"""Async object"""
	
	def __init__(self, thread):
		"""Create async object"""
		self.thread = thread
		self.done = False
		self.error = None
		self.que = queue.Queue()
		
		@thread.listen("WORKER_DONE")
		def _(value):
			self.que.put(value)
			self.done = True
			self.error = thread.error
		
	def get(self):
		"""Wait for thread ending"""
		return self.que.get()
		
class Worker:
	"""Wrap Thread class. 
	
	Use queued message to communicate between threads.
	"""
	
	def __init__(self, target):
		"""init"""
		
		self.target = target
		self.name = str(target)
		self.parent = None
		
		self.thread = None
		self.message_que = queue.Queue()
		self.message_cache = queue.Queue()
		self.children = set()

		self.error = None
		self.running = False
		
		self.is_waiting = False
		self.listeners = {}
		
	def bubble(self, message, param=None, ancestor=True):
		"""Bubble message"""
		if self.parent:
			self.parent.message(message, param, sender=self,
				flag="BUBBLE" if ancestor else None)
	
	def broadcast(self, message, param=None):
		"""Broadcast message"""
		for child in self.children:
			child.message(message, param, sender=self, flag="BROADCAST")
	
	def message(self, message, param=None, sender=None, flag=None):
		"""Create message"""
		ms = Message(message, param, sender, flag)
		self._message(ms)
		return ms
		
	def _message(self, message):
		"""Put message in que or transfer message"""
		if self.running:
			self.message_que.put(message)
		else:
			self.transfer_message(message)
			
	def transfer_message(self, message):
		"""Bubble and broadcast"""
		if message.flag is "BUBBLE" and self.parent:
			if self.parent:
				self.parent._message(message)
			
		if message.flag is "BROADCAST":
			for child in self.children:
				child._message(message)

	def listen(self, message):
		"""This is a decorator. Listen to a specific message.
		
		The arguments of callback function should always be in following forms:
		  def callback():
		  def callback(sender)
		  def callback(<param>)
		  def callback(<param>, sender)
		"""

		if message not in self.listeners:
			self.listeners[message] = []
			
		def listen_message(callback):
			"""Cache callback"""
			sign = inspect.signature(callback)
			count = len(sign.parameters)
			
			def listener(param, sender):
				if count == 0:
					return callback()
				
				elif count == 1 and "sender" in sign.parameters:
					return callback(sender)
					
				elif count == 1:
					return callback(param)
					
				else:
					return callback(param, sender)
				
			self.listeners[message].append(listener)
			
			return callback
			
		return listen_message
		
	def process_message(self, message):
		"""Process message then transfer"""
		
		ret = None
		if message.message in self.listeners:
			for listener in self.listeners[message.message]:
				try:
					ret = listener(message.param, message.sender)
				except Exception as er:
					print("\nIn {} listen {},\n{}".format(
						self.name, message.message, traceback.format_exc()))
					self.error = er
					self.bubble("CHILD_THREAD_ERROR", er, ancestor=False)
		message.put(ret)

		self.transfer_message(message)
		
	def message_loop(self):
		"""Message loop"""
		while True:
			self.wait()
			
	def cleanup(self):
		"""Process message que until empty"""
		while not self.message_cache.empty():
			message = self.message_cache.get_nowait()
			
		while not self.message_que.empty():
			message = self.message_que.get_nowait()
			self.process_message(message)
			
	def wait_message(self, message, sender=None, sync=False):
		"""Wait for specify message"""
		
		while True:
			try:
				ms = self.message_cache.get_nowait()
			except queue.Empty:
				break
			if ms.message == message:
				if sender is None or sender == ms.sender:
					return ms.param

		while True:
			ms = self.message_que.get()
			self.process_message(ms)
			if ms.message == message:
				if sender is None or sender == ms.sender:
					return ms.param
			elif sync:
				self.message_cache.put(ms)

	def wait(self, timeout=None):
		"""Wait some time."""

		# Get any message
		if timeout is None:
			try:
				message = self.message_cache.get_nowait()
			except queue.Empty:
				message = self.message_que.get()
				self.process_message(message)
			return message.param
		
		# Wait some time
		while True:
			ts = time.time()
			try:
				message = self.message_cache.get_nowait()
			except queue.Empty:
				try:
					message = self.message_que.get(timeout=timeout)
				except queue.Empty:
					return
				else:
					self.process_message(message)
			timeout -= time.time() - ts
			if timeout <= 0:
				return
		
	def worker(self, *args, **kwargs):
		"""Real target to pass to threading.Thread"""
		@self.listen("STOP_THREAD")
		def _():
			raise WorkerExit
			
		@self.listen("CHILD_THREAD_START")
		def _(sender):
			self.children.add(sender)
		
		@self.listen("CHILD_THREAD_END")
		def _(sender):
			self.children.remove(sender)
			sender.parent = None
			
		@self.listen("PAUSE_THREAD")
		def _():
			if not self.is_waiting:
				self.is_waiting = True
				self.wait_message("RESUME_THREAD", sync=True)
				self.is_waiting = False

		if not self.parent:
			global_pool.add(self)
			
		self.running = True
		self.bubble("CHILD_THREAD_START", ancestor=False)
		
		returned_value = None
		try:
			if args or kwargs:
				returned_value = self.target(*args, **kwargs)
			else:
				returned_value = self.target(self)
		except WorkerExit:
			pass
		except Exception as er:
			print("\nSomething went wrong in {},\n{}".format(
				self.name, traceback.format_exc()))
			
			if self.running:
				self.error = er
				self.bubble("CHILD_THREAD_ERROR", er, ancestor=False)
			else:
				raise
		self.message("WORKER_DONE", returned_value)
		
		# clean up children
		self.stop_child()
		while self.count_child():
			try:
				self.wait_message("CHILD_THREAD_END")
			except WorkerExit:
				pass

		# clean up message
		while True:
			try:
				self.cleanup()
			except WorkerExit:
				continue
			else:
				break
				
		# clean up listener
		self.listeners = {}
		
		# cleanup status
		self.bubble("CHILD_THREAD_END", returned_value, ancestor=False)
		self.running = False
		
		# clean up global_pool
		if self in global_pool:
			global_pool.remove(self)
		
		return returned_value
			
	def count_child(self, running=True):
		if not running:
			return len(self.children)
			
		count = 0
		for child in self.children:
			if child.running:
				count += 1
		return count
		
	def start(self, *args, **kwargs):
		"""call this method and self.worker will run in new thread"""
		if self.running:
			return
			
		self.thread = threading.Thread(target=self.worker, args=args,
			kwargs=kwargs)
		self.thread.start()
		return self
		
	def stop(self):
		"""Stop self"""
		if self.running:
			self.message("STOP_THREAD")

	def stop_child(self):
		"""Stop all child threads"""
		for child in self.children:
			if child.running:
				child.stop()

	def pause(self):
		"""Pause thread"""
		if self.running and not self.is_waiting:
			self.message("PAUSE_THREAD")

	def resume(self):
		"""Resume thread"""
		self.message("RESUME_THREAD")
		
	def join(self):
		"""thread join method."""
		self.thread.join()
		return self
		
	def create_child(self, target):
		"""Create worker and add to children"""
		child = Worker(target)
		child.parent = self
		return child
		
	def async(*args, **kwargs):
		"""Create async.
		
		This method can be called on Worker class or worker instance.
		  worker.async(func, p0, p1...)
		  Worker.async(func, p0, p1...)
		"""
		if isinstance(args[0], Worker):
			thread = args[0].create_child(args[1])
			args = args[2:]
		else:
			thread = Worker(args[0])
			args = args[1:]
		thread.start(*args, **kwargs)
		return Async(thread)
		
	def await(self, async):
		"""Wait async return"""
		if async.done:
			returned_value = async.returned_value
			error = async.error
		else:
			returned_value = self.wait_message("CHILD_THREAD_END", async.thread)
			error = async.thread.error
			
		if error:
			raise error
			
		return returned_value
		
	def sync(self, func, *args, **kwargs):
		"""Sync call"""
		async = self.async(func, *args, **kwargs)
		return self.await(async)
		
	def is_running(self):
		"""Get worker state"""
		return self.running
		
def global_cleanup():
	pool = global_pool.copy()
	for thread in pool:
		thread.stop()
		thread.join()
		
global_pool = set()
