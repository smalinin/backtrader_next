"""Run every shutdown callback while preserving the original exception."""


class CleanupOnExit:
    def __init__(self, callbacks):
        self._callbacks = callbacks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, primary, original_traceback):
        first_error = primary
        for callback in self._callbacks:
            try:
                callback()
            except BaseException as error:
                if first_error is None:
                    first_error = error
                elif error is not first_error and hasattr(first_error, 'add_note'):
                    first_error.add_note('Cleanup failed: {}: {}'.format(
                        type(error).__name__, error))
                    for note in getattr(error, '__notes__', ()):
                        first_error.add_note(note)
        if primary is not None:
            primary.__traceback__ = original_traceback
        elif first_error is not None:
            raise first_error
        return False
