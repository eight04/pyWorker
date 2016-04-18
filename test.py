#! python3

import threading, worker, gc

from time import sleep

# Basic operations
print("thread operations: start/pause/resume/stop/join")
count = 0
def increaser(thread):
	global count

	@thread.listen("reset")
	def _(event):
		global count
		count = event.data

	while True:
		thread.wait(1)
		count += 1
		print(count)

thread = worker.Worker(increaser).start()
sleep(5.5)
print("time goes 5.5 seconds")
assert count == 5
print("pause thread")
thread.pause()
sleep(2)
assert count == 5
print("reset value")
thread.fire("reset", 0)
sleep(2)
assert count == 0
print("resume thread")
thread.resume()
sleep(0.5)
assert count == 1
print("keep going")
sleep(4)
assert count == 5
print("stop thread")
thread.stop()
sleep(2)
assert count == 5
print("join thread")
thread.join()

print("stop parent thread will cause child to stop too")
parent = worker.Worker()
child = worker.Worker().parent(parent)
parent.start()
child.start()
parent.stop().join()
assert not parent.is_running()
assert not child.is_running()

print("main thread is not daemon thread")
thread = worker.current()
assert not thread.is_daemon()

print("a thread is not daemon thread by the default")
thread = worker.Worker().start()
assert not thread.is_daemon()

print("child thread will inherit default value from parent node")
child = worker.Worker().parent(thread).start()
assert thread.is_daemon() == child.is_daemon()

print("parent should wait till none-daemon child thread stop")
thread.stop().join()
assert not child.is_running()

print("parent thread will not wait till daemon thread end")
def child_worker():
	sleep(1)
parent = worker.Worker()
child = worker.Worker(child_worker, parent=parent, daemon=True)
parent.start()
child.start()
parent.stop().join()
assert child.is_running()
child.join()
assert not child.is_running()

print("a thread will detached from parent on finished")
thread = worker.current()
child = worker.Worker().parent(thread).start()
child.stop()
thread.wait("CHILD_THREAD_END", target=child)
assert child not in thread.children

print("async task, let parent wait child")
thread = worker.current()
def long_work(timeout):
	sleep(timeout)
	return "Finished in {} seconds".format(timeout)
async = thread.async(long_work, 1)
assert thread.await(async) == "Finished in 1 seconds"

print("async task, let child finished before getting")
async = thread.async(long_work, 1)
sleep(2)
assert thread.await(async) == "Finished in 1 seconds"

print("use Async class")
async = worker.Async(long_work, 1)
assert async.get() == "Finished in 1 seconds"
async = worker.Async(long_work, 1)
sleep(2)
assert async.get() == "Finished in 1 seconds"

print("Test bubble/broadcast message")
bubble = False
broadcast = False

parent = worker.Worker()
@parent.listen("Some bubble event")
def _(event):
	global bubble
	bubble = True
	
child = worker.Worker().parent(parent).start()
@child.listen("Some broadcast event")
def _(event):
	global broadcast
	broadcast = True
	
parent.start()
child.start()
	
child.fire("Some bubble event", bubble=True)
parent.fire("Some broadcast event", broadcast=True)

sleep(0.1)

assert bubble
assert broadcast

parent.stop()

print("starting as main will stack on current thread")
class MyWorker(worker.Worker):
	def worker(self, param, hello=None):
		assert param == "Hello world!"
		assert hello == "Hello"
		assert worker.current() is self
MyWorker().start_as_main("Hello world!", hello="Hello").join()

# The folowing tests relate to: http://stackoverflow.com/questions/3752618/python-adding-element-to-list-while-iterating
print("one-time listener")
thread = worker.Worker().start()
@thread.listen("test")
def _(event):
	thread.unlisten(_)
thread.fire("test")

print("listener that add another listener")
@thread.listen("test2")
def _(event):
	def dummy(event):
		print("dummy")
	thread.listen("test2")(dummy)
thread.fire("test2")

thread.stop().join()

print("auto setup parent")
def parent(thread):
	child = worker.Worker().start()
	assert child.parent_node == thread
worker.Worker(parent).start().join()

print("test channel pub/sub")
channel = worker.Channel()
thread = worker.Worker()
channel.sub(thread)
@thread.listen("MY_EVENT")
def _(event):
	assert event.data == "MY_DATA"
thread.start()
channel.pub("MY_EVENT", data="MY_DATA")

print("thread should unsub all channels after GC")
thread.stop().join()
thread = None
gc.collect()
assert len(channel.pool) == 0

print("test listener priority")
access = []
thread = worker.Worker()
@thread.listen("MY_EVENT", priority=3)
def _(event):
	print(3)
	access.append(1)
@thread.listen("MY_EVENT", priority=3)
def _(event):
	print("another 3")
	access.append(2)
@thread.listen("MY_EVENT", priority=3)
def _(event):
	print("3nd 3")
	access.append(3)
@thread.listen("MY_EVENT", priority=1)
def _(event):
	print(1)
	access.append(5)
	thread.exit()
@thread.listen("MY_EVENT", priority=2)
def _(event):
	print(2)
	access.append(4)
thread.start().fire("MY_EVENT").join()
assert access == [1, 2, 3, 4, 5]

print("only main thread is left")
assert len(worker.worker_pool.pool) == 1
assert threading.active_count() == 1
