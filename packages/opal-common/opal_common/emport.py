"""From https://github.com/orweis/emport."""

import collections
import glob
import inspect
import os
import sys

__author__ = "orw"


class ObjectUtils(object):
    @staticmethod
    def is_derived_of(obj, possible_parent_class):
        if hasattr(obj, "__bases__"):
            return possible_parent_class in inspect.getmro(obj)
        else:
            return False

    @staticmethod
    def get_properties(obj):
        def filter(x):
            return not isinstance(x, collections.Callable)

        return {
            k: v for k, v in inspect.getmembers(obj, filter) if not k.startswith("__")
        }

    @staticmethod
    def get_members_who_are_instance_of(obj, class_type):
        def filter(x):
            return isinstance(x, class_type)

        return inspect.getmembers(obj, filter)

    @classmethod
    def get_class_members_who_derive_of(cls, obj, parent_class):
        def filter(x):
            return (
                inspect.isclass(x)
                and cls.is_derived_of(x, parent_class)
                and list(inspect.getmro(x)).index(parent_class) != 0
            )

        return inspect.getmembers(obj, filter)


class PyFrame(object):
    def __init__(self):
        self._frame = inspect.currentframe()

    def __enter__(self):
        return self._frame.f_back

    def __exit__(self, exc_type, exc_value, traceback):
        del self._frame


class Emport(object):
    def __init__(self, module, members):
        self.__original__ = module
        self._members = []
        for member in members:
            self._members.append(member[1])
            setattr(self, member[0], member[1])

    def get_original_module(self):
        return self.__original__

    def get_members_list(self):
        return self._members

    def get_flat_list(self):
        """
        :return: all the members of this Emport (And submodules) as one list
        """
        res = []
        for member in self._members:

            # if a member is an Emport itself flatten it as well
            if isinstance(member, Emport):
                res += member.get_flat_list()
            else:
                res.append(member)
        return res

    def __repr__(self):
        return "EMPORT - %s" % self.__original__


def get_caller_module(depth=0):
    """
    :param depth: stack depth of the caller. 0 == yourself, 1 == your parent
    :return: the module object of the caller function (in set stack depth)
    """
    with PyFrame() as frame:
        for i in range(0, depth):
            frame = frame.f_back
        return sys.modules[frame.f_globals["__name__"]]


def co_to_dict(co):
    return {
        "co_argcount": co.co_argcount,
        "co_nlocals": co.co_nlocals,
        "co_stacksize": co.co_stacksize,
        "co_flags": co.co_flags,
        "co_consts": co.co_consts,
        "co_names": co.co_names,
        "co_varnames": co.co_varnames,
        "co_filename": co.co_filename,
        "co_name": co.co_name,
        "co_firstlineno": co.co_firstlineno,
        "co_lnotab": co.co_lnotab,
    }


def get_caller(depth=0):
    """
    :param depth: stack depth of the caller. 0 == yourself, 1 == your parent
    :return: the frame object of the caller function (in set stack depth)
    """
    with PyFrame() as frame:
        for i in range(0, depth):
            frame = frame.f_back
        return co_to_dict(frame.f_code)


def emport_by_class(from_path, cls, import_items=None):
    """Wrap __import__ to import modules and filter only classes deriving from
    the given cls.

    :param from_path: dot separated package path
    :param cls: class to filter import contents by
    :param import_items: the items to import form the package path (can also be ['*'])
    :return: an Emport object with contents filtered according to given cls
    """
    import_items = import_items or ["*"]
    module_obj = __import__(from_path, globals(), locals(), import_items, 0)
    clean_items = ObjectUtils.get_class_members_who_derive_of(module_obj, cls)
    for (sub_name, sub_module) in ObjectUtils.get_members_who_are_instance_of(
        module_obj, module_obj.__class__
    ):
        results = ObjectUtils.get_class_members_who_derive_of(sub_module, cls)
        # Keep only modules with sub values
        if len(results) > 0:
            clean_sub_module = Emport(sub_module, results)
            clean_items.append((sub_name, clean_sub_module))
    clean_module = Emport(module_obj, clean_items)
    return clean_module


def emport_objects_by_class(from_path, cls, import_items=None):
    """Wrap __import__ to import modules and filter only classes deriving from
    the given cls Return a flat list of objects without the modules themselves.

    :param from_path: dot separated package path
    :param cls: class to filter import contents by
    :param import_items: the items to import form the package path (can also be ['*'])
    :return: an Emport object with contents filtered according to given cls
    """
    results = []
    import_items = import_items or ["*"]
    module_obj = __import__(from_path, globals(), locals(), import_items, 0)
    # direct objects
    clean_items = ObjectUtils.get_class_members_who_derive_of(module_obj, cls)
    results.extend(clean_items)
    # nested
    for (sub_name, sub_module) in ObjectUtils.get_members_who_are_instance_of(
        module_obj, module_obj.__class__
    ):
        objects = ObjectUtils.get_class_members_who_derive_of(sub_module, cls)
        results.extend(objects)
    return results


def dynamic_all(init_file_path):
    """return a list of all the py files in a dir usage (in __init__.py file) :

    from emport import dynamic_all
    __all__ = dynamic_all(__file__)
    """
    modules = glob.glob(os.path.join(os.path.dirname(init_file_path), "*.py*"))
    target_modules = set([])
    for module in modules:
        name = os.path.splitext(os.path.basename(module))[0]
        if os.path.isfile(module) and not name.startswith("_"):
            target_modules.add(name)
    return list(target_modules)
