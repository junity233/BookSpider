from typing import Any, NoReturn, Union
import json
from os.path import exists
from io import open


class FieldNotExistError(Exception):
    field: str

    def __init__(self, field, *args: object) -> None:
        self.field = field
        super().__init__(field, *args)

    def __str__(self) -> str:
        return f'Field "{self.field}" does not exists'


class SettingManager:
    """
        管理设定
        设定分 field,每个需要读取设定的对象都有自己的field.当本field的值更新时会通知对象
    """
    data: dict[str, dict[str, Any]]
    fields: dict[str]
    file_path: str

    def __init__(self, file_path) -> None:
        self.data = {}
        self.fields = {}
        self.file_path = file_path
        self.load()

    def add_field(self, field: str, obj) -> None:
        if field not in self.data.keys():
            self.data[field] = {}
        self.fields[field] = obj

    def remove_field(self, field: str) -> None:
        self.check_field_exist(field)
        del self.fields[field]
        del self.data[field]

    def remove_key(self, field: str, key: str) -> None:
        self.check_field_exist(field)
        if key in self.data[field]:
            del self.data[field][key]

    def get_field(self, field: str) -> dict[str, Any]:
        self.check_field_exist(field)
        return self.data[field]

    def get_field_names(self) -> list[str]:
        return self.data.keys()

    def check_field_exist(self, field: str):
        if field not in self.data.keys():
            raise FieldNotExistError(field)

    def has_key(self, field: str, key: str):
        self.check_field_exist(field)
        return key in self.data[field].keys()

    def get(self, field: str, key: str, value: Any = None, update=True) -> Any:
        """
            获取设置

            `update`:若值更新，是否通知对象
        """
        self.check_field_exist(field)
        if key not in self.data[field].keys():
            self.data[field][key] = value
            if update:
                self.fields[field].update_setting(key, value)
            self.save()

        return self.data[field][key]

    def set(self, field: str, key: str, value: Any, update=True) -> Any:
        """
            设置设置

            `update`:若值更新，是否通知对象
        """
        self.check_field_exist(field)
        self.data[field][key] = value
        if update:
            self.fields[field].update_setting(key, value)
        self.save()

    def save(self) -> None:
        with open(self.file_path, "w") as f:
            json.dump(self.data, f)

    def load(self) -> None:
        if exists(self.file_path):
            with open(self.file_path, "r") as f:
                self.data = json.load(f)


class SettingAccessable:
    """
        可以读取设置的对象基类
        默认field为类名
    """
    _setting_manager: SettingManager
    _setting_field: str

    def __init__(self, setting_manager: SettingManager, field: str = "") -> None:
        self._setting_manager = setting_manager
        if field == "":
            field = self.__class__.__name__

        self._setting_field = field
        self._setting_manager.add_field(field, self)

    def get_setting(self, key: str, value: Any = None) -> Any:
        return self._setting_manager.get(self._setting_field, key, value, update=False)

    def set_setting(self, key: str, value: Any = None) -> Any:
        self._setting_manager.set(
            self._setting_field, key, value, update=False)

    def update_setting(self, key: str, value: Any) -> None:
        pass
