# -*- coding: utf-8 -*-

import logging
import time

logger = logging.getLogger(__name__)

class LoopyWorker:

    def __init__(self):
        self.tasks = []

    def register_task(self, task_name, func, interval, delay=0):
        self.tasks.append(LoopyTask(task_name, func, interval, delay))

    def run(self):
        for t in self.tasks:
            t.run()

    def set_task_interval(self, task_name, new_value):
        return [t.set_interval(new_value) for t in self.tasks if t.name == task_name]


class LoopyTask:

    def __init__(self, name, func, interval, delay):
        self.name = name
        self.func = func
        self.interval = interval
        self.last_execution_time = 0 if delay == 0 else time.time() - interval + delay

    def run(self):
        if time.time() - self.last_execution_time > self.interval:
            self.func()
            self.last_execution_time = time.time()

    def set_interval(self, new_value):
        old_value, self.interval = self.interval, new_value
        return old_value


def main():
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        datefmt='%m-%d %H:%M:%S',
        level=logging.INFO)

    def func1():
        logger.info('hello world!')

    def func2():
        logger.info('how r u?')

    w = LoopyWorker()
    w.register_task('t1', func1, 5)
    w.register_task('t2', func2, 2)
    for _ in range(10):
        w.run()
        time.sleep(1)


if __name__ == '__main__':
    main()
