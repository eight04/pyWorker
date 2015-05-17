pyWorker
========
A threading framework in python.

Usage
-----
Use function as target.
```
from worker import Worker

count = 1

def increaser(thread):
	global count
	while True:
		count += 1
		thread.wait(1)
		
ic = Worker(increaser)
ic.start()

while True:
	command = input("print|pause|resume|stop|exit")
	
	if command == "print":
		print(count)
		
	if command == "pause":
		ic.pause()
		
	if command == "resume":
		ic.resume()
		
	if command == "stop":
		ic.stop()
		
	if command == "exit":
		ic.stop()
		ic.join()
		break
```

Parent, child thread.
```
p_thread = None
c_thread = None

def parent(thread):
	global p_thread, c_thread
	
	p_thread = thread
	c_thread = thread.create_child(child)
	c_thread.start()
	
	thread.message_loop()

def child(thread):
	thread.message_loop()
	
Worker(parent).start()
		
while True:
	command = input("print|stop|exit")
	
	if command == "print":
		print("p_thread.is_running(): {}\nc_thread.is_running(): {}".format(
			p_thread.is_running(),
			c_thread.is_running()
		))
		
	if command == "stop":
		p_thread.stop()
		
	if command == "exit":
		p_thread.stop()
		p_thread.join()
		break
```

Async task.
```
def long_work(t):
	sleep(t)
	return "Finished in {} second(s)".format(t)
	
lw_thread = Worker.async(long_work, 10)

# Do other stuff here...

print(lw_thread.get())
```

Async + parent/child.
```
p_thread = None
c_thread = None

def long_work(t):
	sleep(t)
	return "Finished in {} second(s)".format(t)
	
def parent(thread):
	global p_thread, c_thread
	
	p_thread = thread
	c_thread = thread.async(long_work, 10)
	
	# Do other stuff here...
	
	print(thread.await(c_thread))
	
Worker(parent).start()

while True:
	command = input("print|stop|exit")
	
	if command == "print":
		print("p_thread.is_running(): {}\nc_thread.is_running(): {}".format(
			p_thread.is_running(),
			c_thread.is_running()
		))
		
	if command == "stop":
		p_thread.stop()
		
	if command == "exit":
		p_thread.stop()
		p_thread.join()
		break
```

Message
```
def work(thread):
	@thread.listen("hello")
	def _():
		return "world!"
		
	@thread.listen("ok")
	def _():
		return "cool"
		
	thread.message_loop()
	
w_thread = Worker(work)
w_thread.start()

whil True:
	command = input("<message>|exit")
	
	if command == "exit":
		w_thread.stop()
		w_thread.join()
		
	else:
		message = w_thread.message(command)
		
		# Do other stuff here...
		
		print(message.get())
```

Message + parent/child
```
def odd_man(thread):

	@thread.listen("hey")
	def _(number):
		print(number)
		sleep(1)
		thread.bubble("hey", number + 1)
		
	thread.message_loop()

def even_man(thread):

	@thread.listen("hey")
	def _(number):
		print(number)
		sleep(1)
		thread.broadcast("hey", number + 1)

	od_thread = thread.create_child(odd_man)
	od_thread.start()
	
	thread.message("hey", 0)
	
	thread.message_loop()
	
w_thread = Worker(even_man)

while True:
	command = input("start|stop|exit")
	
	if command == "start":
		w_thread.start()
		
	if command == "stop":
		w_thread.stop()
		
	if command == "exit":
		w_thread.stop()
		w_thread.join()
		break
```
