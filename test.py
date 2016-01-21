#! python3

from time import sleep
from worker import LiveNode, current_thread, Async

print("Thread operations: start/pause/resume/stop/join")

count = 0
def increaser():
	global count
	thread = current_thread()

	@thread.listen("reset")
	def _(event):
		global count
		count = event.data

	while True:
		thread.wait(0.1)
		count += 1

thread = LiveNode(increaser).start()
sleep(0.55)
assert count == 5
thread.pause()
thread.fire("reset", 0)
sleep(0.15)
assert count == 0
thread.resume()
sleep(0.05)
assert count == 1
sleep(0.4)
assert count == 5
thread.stop()
sleep(0.15)
assert count == 5
thread.join()



print("Parent thread will call self.stop_child after finished")

p_thread = None
c_thread = None

def parent():
	global p_thread, c_thread

	p_thread = current_thread()
	c_thread = p_thread.add_child(LiveNode(child).start())

	p_thread.wait(0.1)

def child():
	current_thread().wait(-1)

LiveNode(parent).start()
sleep(0.15)

assert p_thread.is_running() is False
assert c_thread.is_running() is False




print("Create async task")
thread = current_thread()
def long_work(timeout):
	sleep(timeout)
	return "Finished in {} seconds".format(timeout)

async = thread.async(long_work, 0.1)
assert thread.await(async) == "Finished in 0.1 seconds"

print("Another situation")
async = thread.async(long_work, 0.1)
sleep(0.2)
assert thread.await(async) == "Finished in 0.1 seconds"


print("Use Async class")
async = Async(long_work, 0.1)
assert async.get() == "Finished in 0.1 seconds"

print("Another situation")
async = Async(long_work, 0.1)
sleep(0.2)
assert async.get() == "Finished in 0.1 seconds"


print("Create async task on child thread")
def parent():
	thread = current_thread()
	async = thread.async(child, 0.1)
	assert thread.await(async) == "Finished in 0.1 seconds"

def child(timeout):
	sleep(timeout)
	return "Finished in {} seconds".format(timeout)

LiveNode(parent).start().join()




print("Test bubble/broadcast message")
parent_hello = False
child_hello = False
parent_fine = False

def parent():
	thread = current_thread()

	c_thread = thread.add_child(LiveNode(child).start())
	assert c_thread.is_running() is True

	@thread.listen("hello")
	def _(event):
		global parent_hello
		parent_hello = True
		assert c_thread.is_running() is True
		thread.fire("hello", broadcast=True)

	@thread.listen("I'm fine")
	def _(event):
		global parent_fine
		parent_fine = True
		thread.stop()

	thread.wait(-1)

def child():
	thread = current_thread()

	@thread.listen("hello")
	def _(event):
		global child_hello
		child_hello = True
		thread.fire("I'm fine", bubble=True)

	thread.wait(-1)

p_thread = LiveNode(parent).start()
assert p_thread.is_running() is True
p_thread.fire("hello")
p_thread.join()

assert (parent_hello, child_hello, parent_fine) == (True, True, True)



print("Test UserWorker")

test_done = False

class Child(LiveNode):
	def test(self):
		self.fire("test", bubble=True)

class Parent(LiveNode):
	def regist_listener(self):
		super().regist_listener()

		@self.listen("test")
		def _(event):
			global test_done
			test_done = True
			self.stop()

	def worker(self):
		child = self.add_child(Child().start())
		child.test()
		self.wait(-1)

Parent().start().join()

assert test_done is True


print("main thread")
def increaser():
	thread = current_thread()
	count = 0
	while True:
		thread.fire("GIVE_NUMBER", data=count, bubble=True)
		thread.wait(0.1)
		count += 1

thread = current_thread()
listener_len = len(thread.listener_pool)
children_len = len(thread.children)

count = 0
@thread.listen("GIVE_NUMBER")
def give_number_handler(event):
	global count
	assert event.data == count
	count += 1
	if count > 5:
		thread.stop()
		thread.unlisten(give_number_handler)

child = thread.add_child(LiveNode(increaser)).start()

thread.wait(-1)

child.join()

assert len(thread.listener_pool) == listener_len
assert len(thread.children) == children_len
