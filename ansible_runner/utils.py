import sys


class OutputWriter(object):

    def __init__(self, handle):
        self.handle = handle

    def flush(self):
        pass

    def write(self, data):
        sys.stdout.write(data)
        self.handle.write(data)

    def close(self):
        sys.stdout("Process Finished")
        self.handle.close()
