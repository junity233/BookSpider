from .exceptions import *
from .setting import SettingAccessable, SettingManager
from .logger import Loggable


class ProxyProvider(SettingAccessable, Loggable):
    """
        代理类基类
    """

    def __init__(self, setting_manager: SettingManager, field: str = "") -> None:
        super().__init__(setting_manager, field)
        
    @property
    def name(self) -> str:
        return self.__class__.__name__

    def get_http_proxy(self) -> str:
        """
            获取一个http代理

        """
        raise NonimplentException(self.__class__, ProxyProvider.get_http_proxy)

    def get_https_proxy(self) -> str:
        """
            获取一个https代理
        """
        raise NonimplentException(
            self.__class__, ProxyProvider.get_https_proxy)
