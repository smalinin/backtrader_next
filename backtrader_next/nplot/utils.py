#
# Copyright (C) 2015-2023 Sergey Malinin
# GPL 3.0 license <http://www.gnu.org/licenses/>
#

import sys
from contextlib import contextmanager
from tempfile import NamedTemporaryFile, gettempdir
from datetime import datetime

@contextmanager
def tmpfilename():
    with NamedTemporaryFile(suffix='.html') as f:
        if sys.platform.startswith('win'):
            f.close()
        yield f.name

def gen_timestamp():
    now = datetime.now()
    return now.strftime('%Y_%m_%d_%H_%M_%S_%f')

