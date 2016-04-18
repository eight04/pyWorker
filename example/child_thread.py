#! python3

import env

from worker import Worker, sleep

def create_worker(name, parent):
	thread = Worker(parent=parent)
	@thread.listen("HELLO")
	def _(event):
		print(name)
	return thread.start()
	
parent = create_worker("parent", None).start()
child = create_worker("child", parent).start()
grand = create_worker("grand", child).start()
	
# broadcast/bubble is happened in main thread. It doesn't gaurantee
# the execute order of listeners.
parent.fire("HELLO", broadcast=True)
sleep(1)
grand.fire("HELLO", bubble=True)
sleep(1)

# the thread will try to stop its children when thread end
parent.stop()
