from datetime import datetime
from functools import partial
from concurrent.futures import ThreadPoolExecutor, Future
from threading import Lock

from .book import Book, Chapter
from .setting import SettingAccessable, SettingManager
from .database import Database
from .spider import Spider
from .proxy_provider import ProxyProvider
from .logger import Loggable

CONFIG_FILE_NAME = "config.json"


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

    max_threads_count: int

    def __init__(self) -> None:
        self.setting_manager = SettingManager(CONFIG_FILE_NAME)
        SettingAccessable.__init__(self, self.setting_manager)

        self.spiders = {}
        self.proxy_providers = {}
        self.max_threads_count = self.get_setting("max_threads_count", 5)
        self.init_loaded_spiders()

        self.db = Database()
        self.db.open(self.get_setting("database", "books.db"))

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

    def update_chapter(self, chapter: Chapter) -> None:
        if self.db.is_chapter_exist(chapter.book_index, chapter.chapter_index):
            self.db.update_chapter(chapter)
        else:
            self.db.insert_chapter(chapter)

    def update_book(self, book: Book) -> None:
        """
            插入书籍到数据库，若存在则更新，不存在则创建
        """
        with self.db.transaction:
            if self.db.is_book_exist(Source=book.source):
                self.db.get_book_index(book)
                self.db.update_book_all_info(book)
                for chapter in book.chapters:
                    self.update_chapter(chapter)
                self.log_info(f"Book '{book.title}' created.")

            else:
                self.db.create_book(book)
                self.db.insert_chapters(book.chapters)
                self.log_info(f"Book '{book.title}' updated.")

    def get_book(self, url: str, spider: Spider, **params) -> Book:
        """
            使用给定的Spide获取书籍
        """
        book = Book(source=url, spider=spider.name)

        _, menu_data = spider.get_book_info(book, url, **params)

        self.log_info(
            f"Book info : Title = '{book.title}',Author='{book.author}'")

        # 若库中已存在并且是最新的，就跳过这本书，否则获取书籍id
        if self.db.is_book_exist(Source=url):
            book_info = self.db.query_book_info(Source=url)[0]
            if book_info.update != datetime(1970, 1, 1) and book_info.update > book.update:
                return book_info

        menu = spider.get_book_menu(menu_data, **params)
        self.log_info(f"Get chapter info successfully")

        def get_chapter_content_callback(task: Future, chapter: Chapter):
            exception = task.exception()
            if exception:
                self.log_error(
                    f"Get chapter {chapter.title} failed:{exception}")

        chapter_list = []
        with self.get_thread_pool() as thread_pool:
            for idx, chapter_data in menu:
                chapter = book.make_chapter(idx)
                chapter_list.append(chapter)

                task = thread_pool.submit(spider.get_chapter_content,
                                          chapter, chapter_data, **params)
                task.add_done_callback(
                    partial(get_chapter_content_callback, chapter=chapter))

        chapter_list.sort()
        book.chapters = chapter_list
        book.chapter_count = len(chapter_list)

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

    def get_all_book(self, spider: Spider, **params) -> list[Book]:
        book_list = spider.get_all_book(**params)

        res = []
        lock = Lock()

        def get_book_callback(task: Future, book: Book) -> None:
            exception = task.exception()
            if exception:
                self.log_error(
                    f"Get book '{book.title}' source='{book.source}' error:{exception}")
            else:
                with lock:
                    res.append(task.result)

        with self.get_thread_pool() as thread_pool:
            for book in book_list:
                task = thread_pool.submit(
                    self.get_book, book.source, spider, **params)
                task.add_done_callback(partial(get_book_callback, book=book))

        return res

    def query_book(self, **params) -> list[Book]:
        books = self.db.query_book_info(**params)
        return books

    def delete_book(self, book_index: int) -> None:
        self.db.delete_book(book_index)

    def check_book(self, book_index: int, **params) -> None:
        self.db.check_book_exist(Id=book_index)
        book_old = self.db.query_book_info(Id=book_index)[0]

        spider = self.spiders[book_old.spider]

        self.get_book(book_old.source, spider, **params)
        self.log_info("Check book'{}' successfully.")

    def check_all_book(self, **params) -> None:
        book_list = self.db.query_book_info(Status=0)
        for i in book_list:
            spider = self.spiders[i.spider]
            self.get_book(i.source, spider, **params)
        self.log_info("Check book successfully")

    def export_book(self, book_index: int, out_path="") -> None:
        self.db.check_book_exist(Id=book_index)
        book_info = self.query_book(Id=book_index)[0]
        chapters = self.db.query_all_chapters(book_index)

        if out_path == "":
            out_path = book_info.title+".txt"

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(book_info.title+"\n\n")
            f.write(book_info.desc+"-----------------------------------\n")

            for chapter in chapters:
                f.write(chapter.title+"\n")
                f.write(chapter.content+"\n")

        with open(out_path+book_info.cover_format, "wb") as f:
            f.write(book_info.cover)

    def load_spider(self, name: str) -> None:
        spider: Spider = None
        if name in self.spiders.keys():
            return
        try:
            env = {"setting_manager": self.setting_manager}
            exec(f"from spiders.{name} import {name}", env)
            spider = eval(f"{name}(setting_manager)", env)
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
