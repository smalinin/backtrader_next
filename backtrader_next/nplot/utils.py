import sys
from contextlib import contextmanager
from tempfile import NamedTemporaryFile, gettempdir


@contextmanager
def tmpfilename():
    with NamedTemporaryFile(suffix='.html') as f:
        if sys.platform.startswith('win'):
            f.close()
        yield f.name
