from .exceptions import *
from .setting import SettingAccessable, SettingManager
from .logger import Loggable


class ProxyProvider(SettingAccessable, Loggable):
    """
        代理类基类
    """

    def __init__(self, setting_manager: SettingManager, field: str = "") -> None:
        super().__init__(setting_manager, field)

    def get_proxy(self) -> dict[str, str]:
        """
            获取一个代理，按照 `requests` 使用的代理格式返回.e.g:
            ```
            {
                "http":"http://xxxx",
                "https":"http://xxxx"
            }
            ```
        """
        raise NonimplentException(self.__class__, ProxyProvider.get_proxy)
