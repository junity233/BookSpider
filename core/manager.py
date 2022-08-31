from datetime import datetime
from functools import partial
from concurrent.futures import ThreadPoolExecutor, Future
from genericpath import isdir
import logging
import re
from threading import Lock
from os import path
import importlib
from time import sleep
from typing import Union
import aiofiles

from .book import Book, Chapter
from .setting import SettingAccessable, SettingManager
from .database import Database
from .spider import Spider
from .proxy_provider import ProxyProvider
from .logger import Loggable
from .utils import *

CONFIG_FILE_NAME = "config.json"
DEFAULT_DB_FILE = "books.db"


class SpiderNotFoundError(Exception):
    name: str

    def __init__(self, name: str):
        self.name = name
        Exception.__init__(self, name)

    def __str__(self):
        return f"Spider '{self.name}' not found!"


class Manager(Loggable, SettingAccessable):
    setting_manager: SettingManager
    db: Database

    spiders: dict[str, Spider]
    proxy_providers: dict[str, ProxyProvider]

    max_retry: int

    def __init__(self) -> None:
        self.setting_manager = SettingManager(CONFIG_FILE_NAME)
        SettingAccessable.__init__(self, self.setting_manager)

        self.spiders = {}
        self.proxy_providers = {}
        self.max_retry = self.get_setting("max_retry", 5)
        self.init_loaded_spiders()

        self.db = Database()
        self.db.open(self.get_setting("database", DEFAULT_DB_FILE))

    def close(self) -> None:
        for spider in self.spiders.values():
            spider.close()
        self.db.close()

    def get_spider(self, name: str) -> Spider:
        if name not in self.spiders.keys():
            raise SpiderNotFoundError(name)
        return self.spiders[name]

    def get_vaild_spiders(self, url: str, **params) -> list[Spider]:
        """
            根据url获取可以使用的Spider
        """
        res = []
        for _, spider in self.spiders.items():
            if spider.check_url(url, **params):
                res.append(spider)

        return res

    def get_thread_pool(self) -> ThreadPoolExecutor:
        return ThreadPoolExecutor(max_workers=self.max_threads_count)

    def is_book_need_update(self, book: Book) -> bool:
        book_info = self.db.query_book_info(Source=book.source)
        if len(book_info) == 0:
            return True
        if book_info[0].update < book.update or book.update == datetime(1970, 1, 1):
            return True
        return False

    def update_setting(self, key: str, value) -> None:
        if key == "max_retry":
            self.max_retry = value

    def update_book(self, book: Book) -> None:
        """
            插入书籍到数据库，若存在则更新，不存在则创建
        """
        with self.db.transaction:
            if self.db.is_book_exist(Source=book.source):
                self.db.get_book_index(book)
                self.db.update_book_all_info(book)
                for chapter in book.chapters:
                    if self.db.is_chapter_exist(chapter.book_index, chapter.chapter_index):
                        self.db.update_chapter(chapter)
                    else:
                        self.db.insert_chapter(chapter)
                self.log_info(
                    f"Book '{book.title}' updated.index = {book.idx};")

            else:
                self.db.create_book(book)
                self.db.insert_chapters(book.chapters)
                self.log_info(f"Book '{book.title}' created.index={book.idx};")

    def get_book(self, url: str, spider: Spider, **params) -> Union[Book, None]:
        """
            使用给定的Spide获取书籍
        """
        url = convert_url(url)

        book = Book(source=url, spider=spider.name)

        _, menu_data = get_async_result(spider.get_book_info(book, **params))

        self.log_info(
            f"Book info : Title = '{book.title}',Author='{book.author}'")

        book_exist = False
        # 若库中已存在并且是最新的，就跳过这本书，否则获取书籍id
        if self.db.is_book_exist(Source=url):
            book_info = self.db.query_book_info(Source=url)[0]
            book_exist = True
            if book_info.update != datetime(1970, 1, 1) and book_info.update >= book.update:
                self.log_info(f"Book {book_info.title} is already the latest.")
                return book_info
            book.idx = book_info.idx

        menu = get_async_result(spider.get_book_menu(menu_data, **params))
        self.log_info(f"Get chapter info successfully.")

        failed_chapters = []
        chapter_list = []
        chapter_count = 0
        loop = asyncio.get_event_loop()
        tasks = []

        async def get_chapter_content_warpper(chapter: Chapter, chapter_data):
            # 使用这个warpper来捕获异常
            try:
                return await spider.get_chapter_content(chapter, chapter_data, **params)
            except Exception as e:
                self.log_error(f"Get chapter '{chapter.title}' error:{e}")
                logging.exception(e)
                failed_chapters.append((chapter, chapter_data))

        for idx, chapter_data in menu:
            chapter_count += 1
            if book_exist and idx < book_info.chapter_count:
                continue
            chapter = book.make_chapter(idx)
            chapter_list.append(chapter)

            tasks.append(get_chapter_content_warpper(chapter, chapter_data))

        loop.run_until_complete(asyncio.gather(*tasks))

        for _ in range(self.max_retry):
            t = failed_chapters
            failed_chapters = []
            tasks = []

            for chapter, chapter_data in t:
                tasks.append(get_chapter_content_warpper(
                    chapter, chapter_data))
            loop.run_until_complete(asyncio.gather(*tasks))

            if len(failed_chapters) > 0:
                continue
            break
        else:
            return None

        chapter_list.sort()
        book.chapters = chapter_list
        book.chapter_count = chapter_count

        self.update_book(book)

        return book

    def search_book(self, keyword: str, author="", style="", **params) -> list[Book]:
        book_list = []
        book_list_lock = Lock()

        def search_book_callback(task: Future) -> None:
            exception = task.exception()
            if exception:
                self.log_error(f"Search book error:{exception}")
            else:
                res = []
                for book in task.result():
                    res.append(book)
                with book_list_lock:
                    book_list.extend(res)

        with self.get_thread_pool() as thread_pool:
            for _, spider in self.spiders.items():
                task: Future = thread_pool.submit(
                    spider.search_book, keyword, author, style, **params)

                task.add_done_callback(
                    partial(search_book_callback, book_list=book_list, lock=book_list_lock))

        return book_list

    def get_all_book(self, spider: Spider, **params) -> list[int]:
        res = []
        for book in spider.get_all_book(**params):
            for _ in range(self.max_retry):
                try:
                    if self.is_book_need_update(book):
                        t = self.get_book(book.source, spider, **params)
                    else:
                        self.log_info(
                            f"Book '{book.title}' is already the lastest.")
                except Exception as e:
                    self.log_error(
                        f"Get book '{book.title}' source='{book.source}' error:{e}")
                    logging.exception(e)
                else:
                    if t != None:
                        res.append(t.idx)
                    break
                sleep(0.5)

        return res

    def query_book(self, **params) -> list[Book]:
        books = self.db.query_book_info(**params)
        return books

    def delete_book(self, book_index: int) -> None:
        with self.db.transaction:
            self.db.delete_book(book_index)

    def check_book(self, book_index: int, **params) -> None:
        self.db.check_book_exist(Id=book_index)
        book_old = self.db.query_book_info(Id=book_index)[0]

        spider = self.spiders[book_old.spider]

        self.get_book(book_old.source, spider, **params)
        self.log_info(f"Check book'{book_old.title}' successfully.")

    def check_all_book(self, **params) -> None:
        book_list = self.db.query_book_info(Status=0)
        for i in book_list:
            spider = self.spiders[i.spider]
            self.log_info(f"Checking book '{i.title}'...")

            for _ in range(self.max_retry):
                try:
                    self.get_book(i.source, spider, **params)
                except Exception as e:
                    self.log_error(f"Check book {i.title} error:{e}")
                    logging.exception(e)
                    continue
                else:
                    break
        self.log_info("Check all books successfully")

    def export_book(self, book_info: Book, chapters: list[Chapter], out_path=path.curdir) -> None:
        if path.isdir(out_path):
            title = re.sub(r"[\/\\\:\*\?\"\<\>\|]", "_",
                           book_info.title)  # 过滤不合法字符
            out_path = path.join(out_path, title+".txt")

        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(book_info.title+"\n\n")
                f.write(book_info.desc + "\n\n")

                for chapter in chapters:
                    f.write(chapter.title+"\n")
                    f.write(chapter.content+"\n")

            with open(out_path+book_info.cover_format, "wb") as f:
                f.write(book_info.cover)
        except FileNotFoundError:
            self.log_error("Path not found")
        else:
            self.log_info(
                f"Successfully export '{book_info.title}' to {out_path}")

    async def async_export_book(self, book_info: Book, chapters: list[Chapter], out_path=path.curdir) -> None:
        if path.isdir(out_path):
            title = re.sub(r"[\/\\\:\*\?\"\<\>\|]", "_",
                           book_info.title)  # 过滤不合法字符
            out_path = path.join(out_path, title+".txt")

        try:
            async with aiofiles.open(out_path, "w", encoding="utf-8") as f:
                await f.write(book_info.title+"\n\n")
                await f.write(book_info.desc + "\n\n")

                for chapter in chapters:
                    await f.write(chapter.title+"\n")
                    await f.write(chapter.content+"\n")

            async with aiofiles.open(out_path+book_info.cover_format, "wb") as f:
                await f.write(book_info.cover)
        except FileNotFoundError:
            self.log_error("Path not found")
        else:
            self.log_info(
                f"Successfully export '{book_info.title}' to {out_path}")

    def export_book_by_id(self, book_index: int, out_path=path.curdir) -> None:
        self.db.check_book_exist(Id=book_index)
        book_info = self.query_book(Id=book_index)[0]
        chapters = self.db.query_all_chapters(book_index)

        self.export_book(book_info, chapters, out_path)

    def export_all_book(self, out_path=path.curdir) -> None:
        books = self.db.query_book_info()

        tasks = []
        for book in books:
            chapters = self.db.query_all_chapters(book.idx)
            tasks.append(self.async_export_book(book, chapters, out_path))

        with asyncio.get_event_loop() as loop:
            loop.run_until_complete(asyncio.gather(*tasks))

    def load_spider(self, name: str) -> None:
        spider: Spider = None
        if name in self.spiders.keys():
            return
        try:
            spider_module = importlib.import_module(f".{name}", "spiders")
            spider = spider_module.__dict__[name](self.setting_manager)
            if not isinstance(spider, Spider):
                self.log_error("Spider must inherit from Spider class!")

        except ModuleNotFoundError:
            self.log_error(f"Spider {name} not found.")
        except Exception as e:
            self.log_error(f"Add spider '{name}' error:{e}.")
        else:
            self.spiders[spider.name] = spider
            self.log_info(f"Add spider {name} successfully.")

    def init_loaded_spiders(self) -> None:
        for name in self.get_setting("loaded_spiders", []):
            self.load_spider(name)

    def add_spider(self, name: str) -> None:
        self.load_spider(name)
        loaded_spiders = self.get_setting("loaded_spiders", [])
        loaded_spiders.append(name)
        self.set_setting("loaded_spiders", loaded_spiders)

    def remove_spider(self, name: str) -> None:
        if name in self.spiders.keys():
            del self.spiders[name]
            loaded_spiders = self.get_setting("loaded_spiders", [])
            loaded_spiders.remove(name)
            self.set_setting("loaded_spiders", loaded_spiders)
        else:
            raise SpiderNotFoundError(name)

    def load_proxy_provider(self, name: str):
        proxy_provider: ProxyProvider = None
        if name in self.proxy_providers.keys():
            return

        try:
            module = importlib.import_module(f".{name}", "proxy_provider")
            proxy_provider = module.__dict__[name](self.setting_manager)
            if not isinstance(proxy_provider, ProxyProvider):
                self.log_error(
                    "ProxyProvider must inherit from ProxyProvider class.")
                return
        except ModuleNotFoundError:
            self.log_error(f"ProxyProvider '{name}' not found.")
        else:
            self.proxy_providers[name] = proxy_provider
            self.log_info(f"Successfully load ProxyProvider '{name}'")

    def init_loaded_providers(self):
        for name in self.get_setting("proxy_providers", []):
            self.load_proxy_provider(name)

    def add_proxy_provider(self, name):
        self.load_proxy_provider(name)
        providers = self.get_setting("proxy_providers", [])
        providers.append(name)
        self.set_setting("proxy_providers", providers)
