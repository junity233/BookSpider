from datetime import datetime
from functools import partial
from concurrent.futures import ThreadPoolExecutor, Future
from genericpath import isdir
import logging
import os
import re
from threading import Lock
from os import path
import importlib
from time import sleep
from typing import Union
import aiofiles

from core.book_exporter import BookExpoter

from .book import Book, Chapter
from .setting import SettingAccessable, SettingManager
from .database import BookNotExistError, Database
from .spider import Spider
from .proxy_provider import ProxyProvider
from .logger import Loggable
from .utils import *
from .extension_manager import ExtensionManager

CONFIG_FILE_NAME = "config.json"
DEFAULT_DB_FILE = "books.db"


class Manager(Loggable, SettingAccessable):
    setting_manager: SettingManager
    db: Database

    spiders_manager: ExtensionManager
    proxy_providers_manager: ExtensionManager
    book_exporters_manager: ExtensionManager

    max_retry: int

    def __init__(self) -> None:
        self.setting_manager = SettingManager(CONFIG_FILE_NAME)
        SettingAccessable.__init__(self, self.setting_manager)
        Loggable.__init__(self)

        self.spiders_manager = ExtensionManager(
            self.setting_manager, Spider, "spider")
        self.proxy_providers_manager = ExtensionManager(
            self.setting_manager, ProxyProvider, "proxy_provider")
        self.book_exporters_manager = ExtensionManager(
            self.setting_manager, BookExpoter, "book_exporter")
        self.max_retry = self.get_setting("max_retry", 5)

        self.db = Database()
        self.db.open(self.get_setting("database", DEFAULT_DB_FILE))

    def close(self) -> None:
        self.db.close()

    def get_vaild_spiders(self, url: str, **params) -> list[str]:
        """
            根据url获取可以使用的Spider
        """
        res = []
        for k, v in self.spiders_manager.extensions.items():
            if v.check_url(url):
                res.append(k)

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

    def get_book(self, url: str, spider_class: type, **params) -> Union[Book, None]:
        """
            使用给定的Spide获取书籍
        """
        url = convert_url(url)
        spider = spider_class(self.setting_manager)

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
            for _, spider in self.spiders_manager.items():
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

    def query_book(self, limit=-1, offset=-1, *params, **kparams) -> list[Book]:
        books = self.db.query_book_info(limit, offset, *params, **kparams)
        return books

    def delete_book(self, book_index: int) -> None:
        with self.db.transaction:
            self.db.delete_book(book_index)

    def check_book(self, book_index: int, **params) -> None:
        self.db.check_book_exist(Id=book_index)
        book_old = self.db.query_book_info(Id=book_index)[0]

        spider = self.spiders_manager[book_old.spider]

        self.get_book(book_old.source, spider, **params)
        self.log_info(f"Check book'{book_old.title}' successfully.")

    def check_all_book(self, **params) -> None:
        book_list = self.db.query_book_info(Status=0)
        for i in book_list:
            spider = self.spiders_manager[i.spider]
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

    def export_book(self, book: Book, book_exporter_class: type, output: str):
        exporter: BookExpoter = book_exporter_class(self.setting_manager)
        get_async_result(exporter.export_book(book, output))

    def export_books(self, books: list[Book], book_exporter_class: type, output: str):
        exporter: BookExpoter = book_exporter_class(self.setting_manager)
        tasks = []

        for book in books:
            tasks.append(exporter.export_book(book, output))

        loop = asyncio.get_event_loop()
        loop.run_until_complete(asyncio.gather(*tasks))

    def export_book_by_id(self, id: int, book_exporter_class: type, output: str):
        res = self.db.query_book_info(Id=id)
        if len(res) < 0:
            raise BookNotExistError(Id=id)

        book = res[0]
        book.chapters = self.db.query_all_chapters(id)
        book.chapter_count = len(book.chapters)
        self.export_book(book, book_exporter_class, output)
