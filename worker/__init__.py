#! python3

"""Worker

A threaded worker, implemented with message queue and parent/child pattern.
"""

__version__ = "0.2.0"

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
		"""Put returned value. This method used to be called by
		thread.process_message.
		"""
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
			"""Listen to WORKER_DONE"""
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
	
	def __init__(self, target, pass_instance=True, log_message=False,
			log_waiting=False, print_error=True):
		"""init"""
		
		# basic properties
		self.target = target
		self.name = str(target)
		self.pass_instance = pass_instance
		self.error = None
		
		# the thread is a child thread if parent is not None
		self.parent = None
		
		# the child thread will be put in children when starting.
		self.children = set()
		
		# thread and message
		self.thread = None
		self.message_que = queue.Queue()
		self.message_cache = queue.Queue()
		self.listeners = {}

		# thread status
		self.running = False
		self.suspend = False
		
		# debug info
		self.log_message = log_message
		self.log_waiting = log_waiting
		self.print_error = print_error
		
	def bubble(self, message, param=None, ancestor=True):
		"""Bubble message"""
		if self.parent:
			self.parent.message(message, param, sender=self,
				flag="BUBBLE" if ancestor else None)
	
	def broadcast(self, message, param=None):
		"""Broadcast message"""
		children = self.children.copy()
		for child in children:
			child.message(message, param, sender=self, flag="BROADCAST")
	
	def message(self, message, param=None, sender=None, flag=None):
		"""Create message object"""
		if self.log_message:
			print("\n{} create message\n message: {}\n param: {}\n sender: {}"
				"\n flag: {}".format(
					self.name, message, param, sender and sender.name, flag
				))
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
			children = self.children.copy()
			for child in children:
				child._message(message)

	def listen(self, message):
		"""This is a decorator. Listen to a specific message.
		
		The arguments of callback function should always be in following forms:
		  def callback(): pass
		  def callback(sender): pass
		  def callback(<param>): pass
		  def callback(<param>, sender): pass
		  
		Check the source for detail.
		"""

		if message not in self.listeners:
			self.listeners[message] = []
			
		def listen_message(callback):
			"""Decorate callback"""
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
		"""Process and transfer message"""
		
		listeners = (message.message in self.listeners and
			self.listeners[message.message])
		
		if self.log_message:
			print("\n{} process message\n message: {}\n listeners: {}".format(
				self.name,
				message.message,
				listeners))
		
		ret = None
		if listeners:
			for listener in listeners:
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
			
	def wait_message(self, message, sender=None, cache=False):
		"""Wait for specify message"""
		
		if self.log_waiting:
			print("\n{} waiting\n message: {}\n sender: {}".format(
				self.name,
				message, 	
				sender.name
			))
		
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
			elif cache:
				self.message_cache.put(ms)

	def wait(self, timeout=None):
		"""Wait timeout"""

		# Wait for any message
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
		
		self.bubble("CHILD_THREAD_START", ancestor=False)
		
		# pass thread instance
		if self.pass_instance:
			kwargs["thread"] = self
			
		# execute target
		returned_value = None
		try:
			returned_value = self.target(*args, **kwargs)
		except WorkerExit:
			pass
		except Exception as er:
			if self.print_error:
				print("\nSomething went wrong in {},\n{}".format(
					self.name, traceback.format_exc()))
			
			if self.running:
				self.error = er
				self.bubble("CHILD_THREAD_ERROR", er, ancestor=False)
			else:
				raise
		self.message("WORKER_DONE", returned_value)
		
		self.uninit()
		
		self.bubble("CHILD_THREAD_END", returned_value, ancestor=False)
		
		return returned_value
			
	def count_child(self):
		"""Count child threads"""
		return len(self.children)
		
	def init(self):
		"""Init thread, build communication, add listeners"""
		self.running = True
		
		# create communication with parent
		if self.parent:
			self.parent.children.add(self)
			
		# or add to global_pool if no parent
		else:
			global_pool.add(self)
			
		# regist listener
		@self.listen("STOP_THREAD")
		def _():
			raise WorkerExit
			
		@self.listen("PAUSE_THREAD")
		def _():
			if not self.suspend:
				self.suspend = True
				self.wait_message("RESUME_THREAD", cache=True)
				self.suspend = False

	def uninit(self):
		"""End thread"""

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

		# remove communication with parent
		if self.parent:
			self.parent.children.remove(self)
			
		# clean up global_pool
		if self in global_pool:
			global_pool.remove(self)
		
		self.running = False
		
	def start(self, *args, **kwargs):
		"""Start thread"""
		if self.running:
			return self
			
		self.init()
		self.thread = threading.Thread(target=self.worker, args=args,
			kwargs=kwargs)
		self.thread.start()
		return self
		
	def stop(self):
		"""Stop thread"""
		if self.running:
			self.message("STOP_THREAD")
		return self

	def stop_child(self):
		"""Stop all child threads"""
		for child in self.children:
			if child.running:
				child.stop()
		return self

	def pause(self):
		"""Pause thread"""
		if self.running and not self.suspend:
			self.message("PAUSE_THREAD")
		return self

	def resume(self):
		"""Resume thread"""
		self.message("RESUME_THREAD")
		return self
		
	def join(self):
		"""thread join method."""
		self.thread.join()
		return self
		
	def create_child(self, *args, **kwargs):
		"""Create child thread"""
		if issubclass(args[0], UserWorker):
			child = UserWorker(*args[1:], **kwargs)
		else:
			child = Worker(*args, **kwargs)
		
		self.add_child(child)
		
		return child
		
	def add_child(self, child):
		"""Add child thread"""
		if isinstance(child, UserWorker):
			child.thread.parent = self
		else:
			child.parent = self
		return self
		
	def async(*args, **kwargs):
		"""Create async task.
		
		This method can be called on Worker class or thread instance.
		  async = Worker.async(func, p0, p1...)
		  
		  # Do other stuff here...
		  
		  async.get()
		  
		When called on thread instance, the func runs as child thread.
		  async = thread.async(func, p0, p1...)
		  
		  # Do other stuff here...
		  
		  returned_value = thread.await(async)
		"""
		init_args = {}
		for key in ["log_waiting", "log_message", "print_error"]:
			if key in kwargs:
				init_args[key] = kwargs[key]
				del kwargs[key]
				
		if isinstance(args[0], Worker):
			thread = args[0].create_child(args[1], pass_instance=False,
				**init_args)
			args = args[2:]
		else:
			thread = Worker(args[0], pass_instance=False, **init_args)
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
		
class UserWorker:
	"""Wrap Worker object"""
	
	def __init__(self):
		"""Create worker"""
		self.thread = Worker(self.worker, pass_instance=False)
		
	def bubble(self, *args, **kwargs):
		self.thread.bubble(*args, **kwargs)
		
	def broadcast(self, *args, **kwargs):
		self.thread.broadcast(*args, **kwargs)
		
	def message(self, *args, **kwargs):
		self.thread.message(*args, **kwargs)
		
	def listen(self, *args, **kwargs):
		self.thread.listen(*args, **kwargs)
		
	def message_loop(self, *args, **kwargs):
		self.thread.message_loop(*args, **kwargs)
		
	def wait_message(self, *args, **kwargs):
		self.thread.wait_message(*args, **kwargs)
		
	def wait(self, *args, **kwargs):
		self.thread.wait(*args, **kwargs)
		
	def worker(self):
		"""Overwrite"""
		pass
		
	def start(self, *args, **kwargs):
		self.thread.start(*args, **kwargs)
		
	def stop(self, *args, **kwargs):
		self.thread.stop(*args, **kwargs)
		
	def pause(self, *args, **kwargs):
		self.thread.pause(*args, **kwargs)
		
	def resume(self, *args, **kwargs):
		self.thread.resume(*args, **kwargs)
		
	def join(self, *args, **kwargs):
		self.thread.join(*args, **kwargs)
		
	def create_child(self, *args, **kwargs):
		self.thread.create_child(*args, **kwargs)
		
	def add_child(self, *args, **kwargs):
		self.thread.add_child(*args, **kwargs)
		
	def async(self, *args, **kwargs):
		self.thread.async(*args, **kwargs)
		
	def await(self, *args, **kwargs):
		self.thread.await(*args, **kwargs)
		
	def sync(self, *args, **kwargs):
		self.thread.sync(*args, **kwargs)
		
	def is_running(self, *args, **kwargs):
		self.thread.is_running(*args, **kwargs)
		
def global_cleanup():
	"""Clean up threads in global_pool"""
	pool = global_pool.copy()
	for thread in pool:
		thread.stop()
		thread.join()
		
global_pool = set()
