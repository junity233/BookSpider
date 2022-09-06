from email.mime import base
from .logger import Loggable
from .setting import SettingAccessable, SettingManager

import importlib


class ExtensionNotFoundError(Exception):
    module_name: str
    extension_name: str

    def __init__(self, module_name, extension_name):
        self.module_name = module_name
        self.extension_name = extension_name
        Exception.__init__(self, module_name, extension_name)


class ExtensionLoadError(Exception):
    module_name: str
    extension_name: str
    msg: str

    def __init__(self, module_name, extension_name, msg):
        self.module_name = module_name
        self.extension_name = extension_name
        self.msg = msg
        Exception.__init__(self, module_name, extension_name, msg)

    def __str__(self) -> str:
        return self.msg


class ExtensionManager(Loggable, SettingAccessable):
    extensions: dict[str, type]
    module_name: str  # e.g. spider
    base_class: type

    def __init__(self, setting_manager: SettingManager, base_class, module_name) -> None:
        self.base_class = base_class
        self.module_name = module_name
        self.extensions = {}
        Loggable.__init__(self, name=module_name+"_manager")
        SettingAccessable.__init__(
            self, setting_manager, field=f"{module_name}_manager")
        self.init_loaded_extension()

    def get_extension_list(self):
        return self.extensions.keys()

    def init_loaded_extension(self):
        for i in self.get_setting("loaded_list", []):
            self.load_extension(i)

    def load_extension(self, name: str):
        module = importlib.import_module(f'.{name}', self.module_name)
        class_ = module.__dict__[name]
        if not issubclass(class_, self.base_class):
            raise ExtensionLoadError(
                self.module_name, name, "Extension must inherit from base class.")
        self.extensions[name] = class_
        self.log_info(
            f"Module '{self.module_name}' load extension '{name}' successfully")

    def add_extension(self, name: str):
        if name in self.extensions.keys():
            return

        self.load_extension(name)

        ext_list = self.get_setting("loaded_list")
        ext_list.append(name)
        self.set_setting("loaded_list", ext_list)

    def remove_extension(self, name: str):
        if name not in self.extensions.keys():
            raise ExtensionNotFoundError(self.module_name, name)

        del self.extensions[name]
        ext_list = self.get_setting("loaded_list")
        ext_list.remove(name)
        self.set_setting("loaded_list", ext_list)
