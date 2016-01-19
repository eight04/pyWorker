#! python3

from time import sleep
from worker import LiveNode, current_thread

import inspect

print("Test basic start/stop worker")

count = 0
def increaser():
	thread = current_thread()
	global count
	while True:
		thread.wait(1)
		count += 1

thread = LiveNode(increaser).start()
sleep(5.5)
thread.stop()

assert count == 5



print("Parent thread will call self.stop_child after finished")

p_thread = None
c_thread = None

def parent():
	global p_thread, c_thread

	p_thread = current_thread()
	c_thread = p_thread.add_child(LiveNode(child).start())

	p_thread.wait(5)

def child():
	current_thread().wait(-1)

LiveNode(parent).start()
sleep(5.5)

assert p_thread.is_running() is False
assert c_thread.is_running() is False




print("Create async task")
def long_work(timeout):
	sleep(timeout)
	return "Finished in {} seconds".format(timeout)

async = current_thread().async(long_work, 5)
assert async.get() == "Finished in 5 seconds"



print("Create async task on child thread")
def parent():
	thread = current_thread()
	async = thread.async(child, 5)
	assert thread.await(async) == "Finished in 5 seconds"

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
