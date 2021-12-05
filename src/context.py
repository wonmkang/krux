# The MIT License (MIT)

# Copyright (c) 2021 Tom J. Sun

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
import gc
import logging
from display import Display
from input import Input
from camera import Camera
from light import Light

DEFAULT_NETWORK             = 'main'
DEFAULT_PRINTER_BAUDRATE    = 9600
DEFAULT_PRINTER_PAPER_WIDTH = 384
DEFAULT_LOG_LEVEL           = logging.NONE

LOG_FILE = '/sd/.krux.log'

class Context:
    """Context is a singleton containing all 'global' state that lives throughout the
       duration of the program, including references to all device interfaces.
    """

    def __init__(self, version):
        self.net = DEFAULT_NETWORK
        self.printer_baudrate = DEFAULT_PRINTER_BAUDRATE
        self.printer_paper_width = DEFAULT_PRINTER_PAPER_WIDTH
        self.version = version
        self.log = logging.Logger(LOG_FILE, DEFAULT_LOG_LEVEL)
        self.display = Display()
        self.input = Input()
        self.camera = Camera()
        self.light = Light()
        self.printer = None
        self.wallet = None

    def clear(self):
        """Clears all sensitive data from the context, resetting it"""
        self.wallet = None
        if self.printer is not None:
            self.printer.clear()
        gc.collect()

    def debugging(self):
        """Helper method to know if we are in debug mode"""
        return self.log.level <= logging.DEBUG