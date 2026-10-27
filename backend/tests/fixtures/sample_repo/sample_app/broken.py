def ok():
    return 1


def broken():
    pass


class StillFound:
    def method(self):
        return 2


from .gone import nothing
from sample_app.missing_mod import x
