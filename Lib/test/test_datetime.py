import unittest
import sys
import functools

from test.support.import_helper import import_fresh_module


TESTS = 'test.datetimetester'

def load_tests(loader, tests, pattern):
    try:
        fast_tests = import_fresh_module(TESTS, fresh=['datetime', '_strptime'])
    finally:
        # XXX: import_fresh_module() is supposed to leave sys.module cache untouched,
        # XXX: but it does not, so we have to cleanup ourselves.
        for modname in ['datetime', '_datetime', '_strptime']:
            sys.modules.pop(modname, None)

    test_modules = [fast_tests]
    test_suffixes = ["_Fast"]

    for module, suffix in zip(test_modules, test_suffixes):
        test_classes = []
        if module is None:
            continue
        for name, cls in module.__dict__.items():
            if not isinstance(cls, type):
                continue
            if issubclass(cls, unittest.TestCase):
                test_classes.append(cls)
            elif issubclass(cls, unittest.TestSuite):
                suit = cls()
                test_classes.extend(type(test) for test in suit)
        test_classes = sorted(set(test_classes), key=lambda cls: cls.__qualname__)
        for cls in test_classes:
            cls.__name__ += suffix
            cls.__qualname__ += suffix

            @functools.wraps(cls, updated=())
            class Wrapper(cls):
                @classmethod
                def setUpClass(cls_, module=module):
                    cls_._save_sys_modules = sys.modules.copy()
                    sys.modules[TESTS] = module
                    sys.modules['datetime'] = module.datetime_module
                    sys.modules['_datetime'] = module._datetime
                    sys.modules['_strptime'] = module._strptime
                    super().setUpClass()

                @classmethod
                def tearDownClass(cls_):
                    super().tearDownClass()
                    sys.modules.clear()
                    sys.modules.update(cls_._save_sys_modules)

            tests.addTests(loader.loadTestsFromTestCase(Wrapper))
    return tests


if __name__ == "__main__":
    unittest.main()
