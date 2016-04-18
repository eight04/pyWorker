#! python3

import env

from worker import Worker, Channel

def create_worker():
	thread = Worker()
	@thread.listen("PRINT")
	def _(event):
		print(event.data)
	channel.sub(thread)
	return thread.start()

channel = Channel()
thread = create_worker()
channel.pub("PRINT", "Hello channel!")
thread.stop()
