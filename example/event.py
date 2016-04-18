#! python3

import env

from worker import Worker

def create_printer():
	thread = Worker()
	
	@thread.listen("PRINT")
	def _(event):
		print(event.data)
		
	return thread.start()

thread = create_printer()
thread.fire("PRINT", "Hello thread!")
thread.stop()
