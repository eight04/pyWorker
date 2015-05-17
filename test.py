#! python3

from worker import Worker, global_cleanup

def loop(thread):
	thread.message_loop()
	
# if you doesn't hold the reference, the thread become daemon thread.
Worker(loop).start()

# pyWorker provide a cleanup function to stop all threads.
global_cleanup()
