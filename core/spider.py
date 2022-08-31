import re
from time import sleep
from typing import Any, Iterable, Union
import requests
from lxml import etree
from datetime import date, datetime
import mimetypes
import urllib3.exceptions
import cchardet
import aiohttp
import aiohttp.client_exceptions
import asyncio

from .book import Book, Chapter
from .setting import SettingAccessable, SettingManager
from .logger import Loggable
from .exceptions import *
from .utils import get_async_result


class MaxRetriesError(Exception):
    url: str
    params: dict[str, str]
    headers: dict[str, str]
    method: str

    def __init__(self, method, url, params, headers) -> None:
        self.url = url
        self.params = params
        self.headers = headers
        self.method = method

        Exception.__init__(self, method, url, params, headers)

    def __str__(self) -> str:
        return f"Exceeded maximum number of retries:{self.method} {self.url}"


class UnknownCodecError(Exception):
    data: bytes

    def __init__(self, data, *args: object) -> None:
        super().__init__(data, *args)
        self.data = data

    def __str__(self) -> str:
        return "Cannot find a codec for data!"


class Spider(SettingAccessable, Loggable):
    cookie: str
    name: str
    session: aiohttp.ClientSession

    user_agent: str
    timeout: int
    max_retry: int
    semaphore: asyncio.Semaphore

    def __init__(self, setting_manager: SettingManager, field="", name="") -> None:
        if name == "":
            name = self.__class__.__name__
        SettingAccessable.__init__(self, setting_manager, field)
        self.cookie = self.get_setting("cookie", "")
        self.user_agent = self.get_setting(
            "user_agent", r"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36")
        self.session = None
        self.max_retry = self.get_setting("max_retry", 10)
        self.timeout = self.get_setting("timeout", 5)
        self.semaphore = asyncio.Semaphore(self.get_setting("semaphore", 100))

    def create_session(self):
        """
            创建一个aiohttp.ClientSession
        """
        return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))

    async def async_get(self, url: str, params={}, headers: dict[str, str] = {}, use_session=True, **kparams):
        """
            发送Get请求,会重试直到成功获取或超过max_retry
        """

        if self.cookie != "":
            headers["Cookie"] = self.cookie
        headers["User-Agent"] = self.user_agent

        params.update(kparams)

        if self.session == None:
            self.session = self.create_session()

        if self.session.closed:
            self.session = self.create_session()

        for _ in range(self.max_retry):
            try:
                async with self.semaphore:
                    if use_session:
                        return await self.session.get(url=url, headers=headers,
                                                      params=params)
                    else:
                        async with self.create_session() as session:
                            return await session.get(url=url, headers=headers, params=params)
            except aiohttp.client_exceptions.ClientConnectionError as e:
                if e.args[0] == "Connection closed":
                    self.session = self.create_session()
                continue
            except:
                continue

        raise MaxRetriesError("Get", url, params, headers)

    def __del__(self):
        self.close()

    def close(self):
        if self.session:
            get_async_result(self.session.close())

    async def async_get_text(self, url, params: dict[str, str] = {}, headers: dict[str, str] = {}, encoding=None, **kparams) -> str:
        """
            获取网页内容并解码.
            当解码失败时,会对编码进行猜测,若所有猜测都失败,使用str(errors="replace")
        """
        res = await self.async_get(url, headers, params, **kparams)
        for i in range(self.max_retry):
            try:
                return await res.text()
            except UnicodeDecodeError:
                break
            except asyncio.exceptions.TimeoutError:
                continue
            except aiohttp.client_exceptions.ClientConnectionError as e:
                if e.args[0] == "Connection closed":
                    res = await self.async_get(url, headers, params, **kparams)
                    continue
        content: bytes = None

        for i in range(self.max_retry):
            try:
                content = await res.read()
            except:
                continue
            break
        else:
            raise MaxRetriesError("GetText", url, params, headers)

        detect_encoding = cchardet.detect(content)["encoding"]
        probably_charsets = [
            encoding, detect_encoding, "utf-8", "gbk", "gb2312"]

        for i in probably_charsets:
            if i == None:
                continue
            try:
                return content.decode(i)
            except UnicodeDecodeError:
                pass

        if detect_encoding:
            return str(content, encoding=detect_encoding, errors="replace")
        elif res.get_encoding():
            return str(content, encoding=res.get_encoding(), errors="replace")
        else:
            return str(content, encoding='utf-8', errors="replace")

    async def async_get_html(self, url, params: dict[str, str] = {}, headers: dict[str, str] = {}, encoding=None, **kparams) -> etree.Element:
        """
            使用self.get_text获取网页并用 `etree.HTML` 解析
        """
        return etree.HTML(await self.async_get_text(url, params, headers, encoding, **kparams))

    async def async_get_image(self, url) -> tuple[bytes, str]:
        """
            下载图片,返回图片内容和拓展名(根据mimetype猜测)
        """
        img = await self.async_get(url)
        content: bytes = None
        for _ in range(self.max_retry):
            try:
                content = await img.read()
            except asyncio.exceptions.TimeoutError:
                continue
            except aiohttp.client_exceptions.ClientConnectionError as e:
                if e.args[0] == "Connection closed":
                    img = await self.async_get(url)
                continue
            else:
                return content, mimetypes.guess_extension(img.headers["Content-Type"])

        raise MaxRetriesError("GetImage", url, None, None)

    async def async_post(self, url, params: dict = {}, headers: dict = {}, use_session=True, **kparams) -> requests.Response:
        """
            发送Post请求,会重复发送直到成功
        """
        headers.update({
            "user_agent": Spider.user_agent,
            "cookie": self.cookie
        })

        params.update(kparams)

        if self.session == None:
            self.session = self.create_session()

        if self.session.closed:
            self.session = self.create_session()

        for _ in range(self.max_retry):
            try:
                async with self.semaphore:
                    if use_session:
                        return await self.session.post(url=url, headers=headers,
                                                       params=params)
                    else:
                        async with self.create_session() as session:
                            return await session.post(url=url, headers=headers, params=params)
            except aiohttp.ServerTimeoutError:
                continue
            except aiohttp.client_exceptions.ClientConnectionError as e:
                if e.args[0] == "Connection closed":
                    self.session = self.create_session()
                    continue

        raise MaxRetriesError("Post", url, params, headers)

    def get(self, url: str, params={}, headers: dict[str, str] = {}, **kparams):
        """
            使用requests实现的同步get
        """
        if self.cookie != "":
            headers["Cookie"] = self.cookie
        headers["User-Agent"] = self.user_agent

        params.update(kparams)

        for _ in range(self.max_retry):
            try:
                return requests.get(url=url, headers=headers, params=params, timeout=self.timeout)
            except:
                pass

        raise MaxRetriesError("GET", url, params, headers)

    def get_text(self, url: str, params={}, headers: dict[str, str] = {}, encoding=None, **kparams) -> str:
        res = self.get(url, headers, params, **kparams)

        try:
            return res.text
        except UnicodeDecodeError:
            pass
        content: bytes = res.content

        detect_encoding = cchardet.detect(content)["encoding"]
        probably_charsets = [
            encoding, detect_encoding, "utf-8", "gbk", "gb2312"]

        for i in probably_charsets:
            if i == None:
                continue
            try:
                return content.decode(i)
            except UnicodeDecodeError:
                pass

        if detect_encoding:
            return str(content, encoding=detect_encoding, errors="replace")
        elif res.encoding:
            return str(content, encoding=res.encoding, errors="replace")
        else:
            return str(content, encoding='utf-8', errors="replace")

    def get_html(self, url: str, params={}, headers: dict[str, str] = {}, encoding=None, **kparams) -> etree._Element:
        return etree.HTML(self.get_text(url, params, headers, encoding, **kparams))

    def get_image(self, url: str, params={}, headers: dict[str, str] = {}, **kparams) -> tuple[bytes, str]:
        res = self.get(url, params, headers).content
        return res.content, mimetypes.guess_extension(res.headers["Content-Type"])

    def post(self, url: str, params={}, headers: dict[str, str] = {}, **kparams):
        """
            使用requests实现的同步post
        """
        if self.cookie != "":
            headers["Cookie"] = self.cookie
        headers["User-Agent"] = self.user_agent

        params.update(kparams)

        for _ in range(self.max_retry):
            try:
                return requests.post(url=url, headers=headers, data=params, timeout=self.timeout)
            except:
                pass

        raise MaxRetriesError("POST", url, params, headers)

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

    def update_setting(self, key: str, value: Any) -> None:
        if key == "cookie":
            self.cookie = value
        if key == "semaphore":
            self.semaphore = asyncio.Semaphore(value)
        if key == "max_retry":
            self.max_retry = value
        if key == "timeout":
            self.timeout = value
            self.session = self.create_session()

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

    async def get_book_info(self, book: Book,  **params) -> tuple[Book, Any]:
        """
            获取书籍信息，返回一个元组。书籍的Url可以通过 `book.whole_url`获取。
            元组第一项是一个 `Book` ，表示书籍信息。
            第二项是一个任意类型，会被转发给 `get_book_menu`
        """
        raise NonimplentException(
            self.__class__,
            self.get_book_info
        )

    async def get_book_menu(self, data: Any, **params) -> Iterable[tuple[int, Any]]:
        """
            使用 `get_book_info` 返回的信息获取书籍目录。
            返回的目录信息应是一个可以迭代的对象，每次迭代返回一个元组，包含章节序号和信息。
            章节信息不一定是一个Url,可以是一个dict以包含更多信息。这些信息会原封不动地转发给`get_chapter_content`方法
        """
        raise NonimplentException(
            self.__class__,
            self.get_book_menu
        )

    async def get_chapter_content(self, chapter: Chapter, data: Any, **params) -> Chapter:
        """
            使用给定的章节信息来获取章节内容。
            获取到的内容应填充到 `chapter` 中。
            返回值就是这个 `chapter`。

            注意，这是一个异步方法
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

            这是一个迭代器
        """
        raise NonimplentException(
            self.__class__,
            self.get_all_book
        )
