import re
from typing import Any, Iterable, Union
import requests
from lxml import etree
from datetime import date, datetime
import mimetypes
import urllib3.exceptions

from .book import Book, Chapter
from .setting import SettingAccessable, SettingManager
from .logger import Loggable
from .exceptions import *


class Spider(SettingAccessable, Loggable):
    cookie: str
    name: str

    user_agent: str
    timeout: int = 5

    def __init__(self, setting_manager: SettingManager, field="", name="") -> None:
        if name == "":
            name = self.__class__.__name__
        SettingAccessable.__init__(self, setting_manager, field)
        self.cookie = self.get_setting("cookie", "")
        self.user_agent = self.get_setting(
            "user_agent", r"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36")

    def get(self, url: str, params={}, headers: dict[str, str] = {}, **kparams) -> requests.Response:
        """
            发送Get请求,会重试直到成功获取
        """

        if self.cookie != "":
            headers["Cookie"] = self.cookie
        headers["User-Agent"] = self.user_agent

        params.update(kparams)

        res = None
        while True:
            try:
                res = requests.get(url=url, headers=headers,
                                   params=params, timeout=Spider.timeout)
            except requests.Timeout:
                continue
            except requests.ConnectionError as e:
                if isinstance(e.args[0], urllib3.exceptions.MaxRetryError):
                    continue

                raise e
            else:
                break

        return res

    def get_html(self, url, params: dict[str, str] = {}, headers: dict[str, str] = {}, **kparams) -> etree.Element:
        """
            使用self.get获取网页并用 `etree.HTML` 解析
        """
        res = self.get(url, headers, params, **kparams)
        return etree.HTML(res.text)

    def get_image(self, url):
        img = self.get(url)
        return img.content, mimetypes.guess_extension(img.headers["Content-Type"])

    @ staticmethod
    def get_ele_content(ele: etree._Element) -> str:
        res = ""
        if ele.text:
            res += ele.text

        for i in ele:
            if i.tag == "br":
                res += '\n'
            if i.tail:
                res += i.tail

        return res

    @ staticmethod
    def match_date(s: str):
        res = re.search(r"(\d{2,4})(\-|\/|.)(\d{1,2})\2(\d{1,2})", s)
        if res:
            year = int(res.group(1))
            month = int(res.group(3))
            day = int(res.group(4))

            if year < 1000:
                year += 1000
            return datetime(year, month, day)
        else:
            return datetime(1970, 1, 1)

    def post(self, url, params: dict = {}, headers: dict = {}, **kparams) -> requests.Response:
        """
            发送Post请求,会重复发送直到成功
        """
        headers.update({
            "user_agent": Spider.user_agent,
            "cookie": self.cookie
        })

        params.update(kparams)

        res = None
        while True:
            try:
                res = requests.post(url=url, headers=headers,
                                    data=params, timeout=Spider.timeout)
            except requests.Timeout:
                pass
            else:
                break

        return res

    def update_setting(self, key: str, value: Any) -> None:
        if key == "cookie":
            self.cookie = value

    def post_json(self, url, params: dict = {}, headers: dict = {}, **kparams) -> dict[str, object]:
        """
            使用 `self.post` 发送请求并解码json
        """
        return self.post(url, params, headers, **kparams).json()

    def make_book(self, title="", author="", source="", desc="", style="", idx=-1, chapter_count=0, cover=None, cover_format=None, status=True, update=datetime(1970, 1, 1), publish=datetime(1970, 1, 1)):
        return Book(
            title, author, source, self.name, desc, style, idx, chapter_count, cover, cover_format, status, update, publish
        )

    def check_url(self, url: str, **params) -> bool:
        """
            检查URL是否可以被该Spider爬取
        """
        raise NonimplentException(
            self.__class__,
            self.check_url
        )

    def get_book_info(self, book: Book,  **params) -> tuple[Book, Any]:
        """
            获取书籍信息，返回一个元组。书籍的Url可以通过 `book.whole_url`获取。
            元组第一项是一个 `Book` ，表示书籍信息。
            第二项是一个任意类型，会被转发给 `get_book_menu`
        """
        raise NonimplentException(
            self.__class__,
            self.get_book_info
        )

    def get_book_menu(self, data: Any, **params) -> Iterable[tuple[int, Any]]:
        """
            使用 `get_book_info` 返回的信息获取书籍目录。
            返回的目录信息应是一个可以迭代的对象，每次迭代返回一个元组，包含章节序号和信息。
            章节信息不一定是一个Url,可以是一个dict以包含更多信息。这些信息会原封不动地转发给`get_chapter_content`方法
        """
        raise NonimplentException(
            self.__class__,
            self.get_book_menu
        )

    def get_chapter_content(self, chapter: Chapter, data: Any, **params) -> Chapter:
        """
            使用给定的章节信息来获取章节内容。
            获取到的内容应填充到 `chapter` 中。
            返回值就是这个 `chapter`
        """
        raise NonimplentException(
            self.__class__,
            self.get_chapter_content
        )

    def search_book(self, keyword: str, author="", style="", **params) -> Iterable[Book]:
        """
            使用给定的信息查询书籍。
        """
        raise NonimplentException(
            self.__class__,
            self.search_book
        )

    def get_all_book(self, **param) -> Iterable[Book]:
        """
            获取所有的书籍列表,只需要书籍的title与source
        """
        raise NonimplentException(
            self.__class__,
            self.get_all_book
        )
