from xxlimited import Str
from core.proxy_provider import ProxyProvider
from core.logger import Loggable
from core.setting import SettingAccessable, SettingManager

class SimpleProxyProvider(ProxyProvider):
    http_proxy:str
    https_proxy:str
    
    def __init__(self,setting_manager:SettingManager)->None:
        ProxyProvider.__init__(self,setting_manager)
        self.http_proxy=self.get_setting("http","")
        self.https_proxy=self.get_setting("https","")
    
    def get_http_proxy(self) -> str:
        return self.http
    
    def get_https_proxy(self) -> str:
        return self.https

    def update_setting(self, key: str, value) -> None:
        if key=="http":
            self.http=value
        if key=="https":
            self.https=value
        
        super().update_setting(key, value)
        
        