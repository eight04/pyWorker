#! python3

import unittest
import worker
import time
import gc
import threading

class TestWorker(unittest.TestCase):
	
	def test_basic_operations(self):
		"""start/pause/resume/stop/join"""
		a = 0
		
		@worker.Worker
		def increaser():
			nonlocal a

			@worker.listen("set")
			def _(event):
				nonlocal a
				a = event.data

			while True:
				worker.sleep(1)
				a += 1
				
		increaser.start()
		
		with self.subTest("basic"):		
			time.sleep(5.5)
			self.assertEqual(a, 5)
		
		with self.subTest("pause"):
			increaser.pause()			
			time.sleep(2)
			self.assertEqual(a, 5)
			
		with self.subTest("event works even the thread is paused"):
			increaser.fire("set", 0)
			time.sleep(2)
			self.assertEqual(a, 0)
		
		with self.subTest("resume"):
			increaser.resume()
			time.sleep(0.5)
			self.assertEqual(a, 1)
		
		with self.subTest("keep going"):
			time.sleep(4)
			self.assertEqual(a, 5)

		with self.subTest("stop"):
			increaser.stop()
			time.sleep(2)
			self.assertEqual(a, 5)
		
		increaser.join()
		
	def test_child_thread(self):
		parent = worker.Worker()
		child = worker.Worker(parent=parent)
		
		parent.start()
		child.start()
		
		parent.stop().join()
		
		self.assertFalse(parent.is_running())
		self.assertFalse(child.is_running())
		
	def test_daemon(self):
		with self.subTest("main thread is not deamon"):
			thread = worker.current()
			self.assertFalse(thread.is_daemon())
		
		with self.subTest("thread is not daemon by default"):
			a = worker.Worker().start()
			self.assertFalse(thread.is_daemon())
			a.stop().join()
		
		with self.subTest("should inherit parent if not set"):
			a = worker.Worker(daemon=True).start()
			self.assertTrue(a.is_daemon())
			
			b = worker.Worker(parent=a).start()
			self.assertTrue(b.is_daemon())
			
			a.stop().join()
			
		with self.subTest("parent will wait non-daemon child thread"):
			a = worker.Worker().start()
			b = worker.Worker(parent=a).start()
			a.stop().join()
			self.assertFalse(b.is_running())
			
		with self.subTest("parent won't wait daemon child thread"):
			def waiter():
				time.sleep(1)
			a = worker.Worker().start()
			b = worker.Worker(waiter, parent=a, daemon=True).start()
			a.stop().join()
			self.assertTrue(b.is_running())
			b.join()
			
	def test_detached(self):
		"""child will detached from parent when finished"""
		a = worker.Worker().start()
		b = worker.Worker(parent=a).start()
		b.stop().join()
		time.sleep(1)
		self.assertNotIn(b, a.children)
		a.stop().join()
		
	def test_async(self):
		thread = worker.current()
		
		def long_work(timeout):
			time.sleep(timeout)
			return "Finished after {timeout}".format(timeout=timeout)
		
		with self.subTest("parent wait child"):
			async = thread.async(long_work, 1)
			self.assertEqual(thread.wait(async), "Finished after 1")
			
		with self.subTest("child wait parent"):
			async = thread.async(long_work, 1)
			time.sleep(2)
			self.assertEqual(thread.wait(async), "Finished after 1")
			
		# use Async class
		with self.subTest("parent wait child"):
			async = worker.Async(long_work, 1)
			self.assertEqual(async.get(), "Finished after 1")
			
		with self.subTest("child wait parent"):
			async = worker.Async(long_work, 1)
			time.sleep(2)
			self.assertEqual(async.get(), "Finished after 1")
			
	def test_event(self):
		access = {}
		
		a = worker.Worker().start()
		b = worker.Worker(parent=a).start()
		c = worker.Worker(parent=b).start()
		
		@a.listen("MY_BUBBLE")
		def _(event):
			access["bubble"] = event.target
			
		@c.listen("MY_BROADCAST")
		def _(event):
			access["broadcast"] = event.target
			
		a.broadcast("MY_BROADCAST")
		c.bubble("MY_BUBBLE")
		
		time.sleep(1)
		
		self.assertEqual(access, {
			"bubble": c,
			"broadcast": a
		})
		
		a.stop().join()
		
	def test_overlay(self):
		"""Use start_overlay to start worker on current thread"""
		def my_worker(thread):
			self.assertTrue(worker.is_main(thread))
		worker.Worker(my_worker).start_overlay()
		
	def test_thread_safe(self):
		"""
		These tests are related to:
		http://stackoverflow.com/q/3752618
		
		I'm not even sure if these tests are correct.
		"""
		with self.subTest("one-time listener"):
			a = worker.Worker().start()
			@a.listen("test")
			def _(event):
				a.unlisten(_)
			a.fire("test")
			a.stop().join()
			self.assertNotIn(_, a.listener_pool)
			self.assertEqual(a.listeners.get("test", []), [])
			
		with self.subTest("add listener in listener callback"):
			a = worker.Worker().start()
			@a.listen("test")
			def _(event):
				@a.listen("test")
				def _(event):
					pass
			a.fire("test")
			a.stop().join()
			self.assertEqual(len(a.listeners.get("test", [])), 2)
			
	def test_default_parent(self):
		"""When creating thread in non-main thread, the parent of the created
		thread will be set to current thread.
		"""
		b = None
		def maker(thread):
			nonlocal b
			b = worker.Worker().start()
			thread.wait_forever()
		a = worker.Worker(maker).start()
		a.stop().join()
		self.assertEqual(b.parent_node, a)
		
	def test_channel(self):
		access = set()
		workers = set()
		ch = worker.Channel()
		
		def new_worker():
			w = worker.Worker()
			workers.add(w)
			@w.listen("MY_EVENT")
			def _(event):
				access.add(w)
			ch.sub(w)
			w.start()
		
		for i in range(10):
			new_worker()
			
		ch.pub("MY_EVENT")
		
		time.sleep(1)
		
		self.assertEqual(workers, access)
		
		for w in workers:
			w.stop().join()
			
		with self.subTest("automatically unsub after GC"):
			w = None
			workers = None
			access = None
			gc.collect()
			self.assertEqual(len(ch.pool), 0)
			
	def test_priority(self):
		access = []
		thread = worker.Worker()
		
		def register(i, priority):
			@thread.listen("MY_EVENT", priority=priority)
			def _(event):
				access.append(i)
				
		for i, p in enumerate([1, 3, 3, 1, 2]):
			register(i, p)
			
		thread.start().fire("MY_EVENT").stop().join()
		
		self.assertEqual(access, [1, 2, 4, 0, 3])
		
	def test_later(self):
		a = 0
		b = None
		def add(value):
			nonlocal a
			nonlocal b
			b = worker.current()
			a += value
		worker.later(add, 2, 10)
		
		with self.subTest("not yet"):
			worker.sleep(1)
			self.assertEqual(a, 0)
			self.assertEqual(b, None)
		
		with self.subTest("finished"):
			worker.sleep(2)
			self.assertEqual(a, 10)
			self.assertEqual(b, worker.current())
			
	def tearDown(self):
		bad_threads = []
		
		for ws in list(worker.worker_pool.pool.values()):
			w = ws[-1]
			if not worker.is_main(w):
				w.stop().join()
				bad_threads.append(w)
				
		self.assertEqual(bad_threads, [])
		self.assertEqual(threading.active_count(), 1)
		
	
if __name__ == "__main__":
	unittest.main()
