#! python3

from time import sleep
from worker import LiveNode, current_thread, Async


# Basic operations
print("thread operations: start/pause/resume/stop/join")
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

print("stop parent thread will cause child to stop too")
parent = LiveNode().start()
child = parent.add_child(LiveNode(daemon=True)).start()
parent.stop().join()
child.stop().join()
assert not parent.is_running()
assert not child.is_running()

print("main thread is not daemon thread")
thread = current_thread()
assert not thread.is_daemon()

print("a thread is not daemon thread by the default")
thread = LiveNode().start()
assert not thread.is_daemon()

print("child thread will inherit default value from parent node")
child = thread.add_child(LiveNode()).start()
assert thread.is_daemon() == child.is_daemon()

print("parent should wait till none-daemon child thread stop")
thread.stop().join()
assert not child.is_running()

print("a self-destroy thread will detach from parent on finished")
child = current_thread().add_child(LiveNode(self_destroy=True)).start()
child.stop().join()
assert child not in current_thread().children

print("async task, let parent wait child")
thread = current_thread()
def long_work(timeout):
	sleep(timeout)
	return "Finished in {} seconds".format(timeout)
async = thread.async(long_work, 0.1)
assert thread.await(async) == "Finished in 0.1 seconds"

print("async task, let child finished before getting")
async = thread.async(long_work, 0.1)
sleep(0.2)
assert thread.await(async) == "Finished in 0.1 seconds"

print("use Async class")
async = Async(long_work, 0.1)
assert async.get() == "Finished in 0.1 seconds"
async = Async(long_work, 0.1)
sleep(0.2)
assert async.get() == "Finished in 0.1 seconds"

print("Test bubble/broadcast message")
parent = LiveNode().start()
child = parent.add_child(LiveNode).start()
bubble = False
broadcast = False

@parent.listen("Some bubble event")
def _(event):
	global bubble
	bubble = True
child.fire("Some bubble event", bubble=True)

@child.listen("Some broadcast event")
def _(event):
	global broadcast
	broadcast = True
parent.fire("Some broadcast event", broadcast=True)

sleep(0.1)

assert bubble
assert broadcast

parent.stop()

print("starting as main will stack on current thread")
class MyWorker(LiveNode):
	def worker(self, param, hello=None):
		assert param == "Hello world!"
		assert hello == "Hello"
		assert current_thread() is self
MyWorker().start_as_main("Hello world!", hello="Hello").join()

print("RootNode join")
current_thread().join()
