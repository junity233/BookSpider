import re
from time import sleep
from typing import Any, Iterable, Union
import requests
from lxml import etree
from datetime import date, datetime
import mimetypes
import urllib3.exceptions
import chardet
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
        Loggable.__init__(self)
        self.cookie = self.get_setting("cookie", "")
        self.user_agent = self.get_setting(
            "user_agent", r"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36")
        self.session = None
        self.max_retry = self.get_setting("max_retry", 10)
        self.timeout = self.get_setting("timeout", 5)
        self.semaphore = asyncio.Semaphore(self.get_setting("semaphore", 100))

    def create_session(self):
        """
            ????????????aiohttp.ClientSession
        """
        return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))

    async def async_get(self, url: str, params={}, headers: dict[str, str] = {}, use_session=True, **kparams):
        """
            ??????Get??????,????????????????????????????????????max_retry
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
            ???????????????????????????.
            ??????????????????,????????????????????????,????????????????????????,??????str(errors="replace")
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

        detect_encoding = chardet.detect(content)["encoding"]
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
            ??????self.get_text?????????????????? `etree.HTML` ??????
        """
        return etree.HTML(await self.async_get_text(url, params, headers, encoding, **kparams))

    async def async_get_image(self, url) -> tuple[bytes, str]:
        """
            ????????????,??????????????????????????????(??????mimetype??????)
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
            ??????Post??????,???????????????????????????
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
            ??????requests???????????????get
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

        detect_encoding = chardet.detect(content)["encoding"]
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
            ??????requests???????????????post
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

    @staticmethod
    def check_url(url: str, **params) -> bool:
        """
            ??????URL??????????????????Spider??????
        """
        raise NonimplentException(
            Spider,
            Spider.check_url
        )

    async def get_book_info(self, book: Book,  **params) -> tuple[Book, Any]:
        """
            ???????????????????????????????????????????????????Url???????????? `book.whole_url`?????????
            ???????????????????????? `Book` ????????????????????????
            ???????????????????????????????????????????????? `get_book_menu`
        """
        raise NonimplentException(
            self.__class__,
            self.get_book_info
        )

    async def get_book_menu(self, data: Any, **params) -> Iterable[tuple[int, Any]]:
        """
            ?????? `get_book_info` ????????????????????????????????????
            ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
            ??????????????????????????????Url,???????????????dict???????????????????????????????????????????????????????????????`get_chapter_content`??????
        """
        raise NonimplentException(
            self.__class__,
            self.get_book_menu
        )

    async def get_chapter_content(self, chapter: Chapter, data: Any, **params) -> Chapter:
        """
            ???????????????????????????????????????????????????
            ?????????????????????????????? `chapter` ??????
            ????????????????????? `chapter`???

            ?????????????????????????????????
        """
        raise NonimplentException(
            self.__class__,
            self.get_chapter_content
        )

    def search_book(self, keyword: str, author="", style="", **params) -> Iterable[Book]:
        """
            ????????????????????????????????????
        """
        raise NonimplentException(
            self.__class__,
            self.search_book
        )

    def get_all_book(self, **param) -> Iterable[Book]:
        """
            ???????????????????????????,??????????????????title???source

            ?????????????????????
        """
        raise NonimplentException(
            self.__class__,
            self.get_all_book
        )
