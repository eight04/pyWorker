#! python3

from worker import Worker, global_cleanup
from time import sleep

import inspect

print("Test basic start/stop worker")

count = 0
def increaser(thread):
	global count
	while True:
		thread.wait(1)
		count += 1
ic_thread = Worker(increaser).start()
sleep(5.5)
ic_thread.stop()

assert count == 5



print("Child thread should stop when parent thread is done")

p_thread = None
c_thread = None

def parent(thread):
	global p_thread, c_thread
	
	p_thread = thread
	c_thread = thread.create_child(child).start()
	
	thread.wait(5)
	
def child(thread):
	thread.message_loop()
	
Worker(parent).start()
sleep(5.5)

assert p_thread.is_running() is False
assert c_thread.is_running() is False




print("Create async task")
def long_work(timeout):
	sleep(timeout)
	return "Finished in {} seconds".format(timeout)
	
async = Worker.async(long_work, 5)
assert async.get() == "Finished in 5 seconds"
		
		
		
print("Create async task on child thread")
def parent(thread):
	async = thread.async(child, 5)
	assert thread.await(async) == "Finished in 5 seconds"
	
def child(timeout):
	sleep(timeout)
	return "Finished in {} seconds".format(timeout)
	
Worker(parent).start().join()



print("Test message")
def background(thread):
	@thread.listen("hello")
	def dummy():
		return "world!"
		
	@thread.listen("ok")
	def dummy():
		return "cool"
		
	thread.message_loop()
	
bg_thread = Worker(background).start()

message = bg_thread.message("hello")
assert message.get() == "world!"

message = bg_thread.message("ok")
assert message.get() == "cool"

bg_thread.stop().join()



print("Test bubble/broadcast message")
parent_hello = False
child_hello = False
parent_fine = False

def parent(thread):
	c_thread = thread.create_child(child).start()
	assert c_thread.is_running() is True
	
	@thread.listen("hello")
	def dummy():
		global parent_hello
		parent_hello = True
		assert c_thread.is_running() is True
		thread.broadcast("hello")
		
	@thread.listen("I'm fine")
	def dummy():
		global parent_fine
		parent_fine = True
		thread.stop()
		
	thread.message_loop()
	
def child(thread):

	@thread.listen("hello")
	def dummy():
		global child_hello
		child_hello = True
		thread.bubble("I'm fine")
		
	thread.message_loop()

p_thread = Worker(parent).start()
assert p_thread.is_running() is True
p_thread.message("hello")
p_thread.join()

assert (parent_hello, child_hello, parent_fine) == (True, True, True)
		
		
		
print("Test global_cleanup")

def loop(thread):
	thread.message_loop()
	
l_thread = Worker(loop).start()

global_cleanup()

assert l_thread.is_running() is False
	
