from genericpath import isdir, isfile
import os
from .exceptions import NonimplentException
from .setting import SettingAccessable, SettingManager
from .logger import Loggable
from .book import Book, Chapter


class BookExpoter(SettingAccessable, Loggable):
    """
        书籍导出器的基类
    """

    def __init__(self, setting_manager: SettingManager) -> None:
        SettingAccessable.__init__(self, setting_manager)
        Loggable.__init__(self)

    @staticmethod
    def fix_path(path, title="book", ext=".txt"):
        if os.path.isdir(path):
            path = os.path.join(path, title+ext)
        elif not os.path.isfile(path):
            os.mkdir(path)
            path = os.path.join(path, title+ext)

        return path

    async def export_book(self, book: Book, output: str):
        """
            导出书籍，异步执行
        """
        raise NonimplentException(self.__class__, BookExpoter.export_book)
