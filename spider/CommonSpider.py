from core.spider import Spider
from core.book import Book, Chapter
from core.setting import SettingManager
from typing import Any


class CommonSpider(Spider):
    name = "CommonSpider"

    def __init__(self, setting_manager: SettingManager) -> None:
        super().__init__(setting_manager)

    def get_book_info(self, book: Book, **params) -> tuple[Book, Any]:
        return super().get_book_info(book, **params)
