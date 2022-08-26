from datetime import datetime
import sqlite3
from threading import RLock
from tkinter.messagebox import NO
from turtle import update

from .spider import Spider
from .book import Book, Chapter
from .logger import Loggable


class BookNotExistError(Exception):
    args: int

    def __init__(self, *args: object) -> None:
        self.args = args
        Exception.__init__(self, *args)

    def __str__(self) -> str:
        return f'Book {self.args} does not exists'


class Transaction:
    db: object

    def __init__(self, db: object) -> None:
        self.db = db

    def __enter__(self) -> None:
        with self.db.db_lock:
            self.db.connection.execute("Begin Transaction;")

    def __exit__(self, exception_type, exception_value, traceback) -> None:
        if exception_type:
            self.db.rollback()
            return False
        else:
            self.db.commit()


class ChapterNotExistError(Exception):
    book_index: int
    chapter_index: int

    def __init__(self, book_index: int, chapter_index: int, *args: object) -> None:
        self.book_index = book_index
        self.chapter_index = chapter_index

        Exception.__init__(self, book_index, chapter_index)

    def __str__(self) -> str:
        return f'Chapter {self.chapter_index} of Book {self.book_index} does not exists'


class UnsupportedType(Exception):
    type_: type

    def __init__(self, type_: type, *args: object) -> None:
        super().__init__(*args)
        self.type_ = type

    def __str__(self) -> str:
        return f'Type "{self.type_}" is not supported'


class Database(Loggable):
    connection: sqlite3.Connection
    cursor: sqlite3.Cursor

    db_lock: RLock

    def __init__(self, db_file_path: str = "") -> None:
        self.db_lock = RLock()
        self.connection = None
        self.cursor = None

        if db_file_path != "":
            self.open(db_file_path)

    def query(self, sql, *params) -> list[tuple]:
        res = None
        with self.db_lock:
            self.cursor.execute(sql, *params)
            res = self.cursor.fetchall()
        return res

    def fetchall(self) -> list:
        res = None
        with self.db_lock:
            res = self.cursor.fetchall()
        return res

    def execute(self, sql, *params) -> None:
        with self.db_lock:
            self.cursor.execute(sql, *params)

    def executemany(self, sql, *params) -> None:
        with self.db_lock:
            self.cursor.executemany(sql, *params)

    def commit(self) -> None:
        with self.db_lock:
            self.connection.commit()

    def rollback(self) -> None:
        with self.db_lock:
            self.connection.rollback()

    def close(self) -> None:
        if self.connection:
            self.cursor.close()
            self.connection.close()
            self.cursor = self.connection = None

    @property
    def transaction(self) -> Transaction:
        return Transaction(self)

    def open(self, db_file_path: str) -> None:
        self.connection = sqlite3.connect(
            db_file_path, check_same_thread=False, isolation_level='')
        self.cursor = self.connection.cursor()
        self.check_primary_table_exist()
        self.log_info(f"Load database '{db_file_path}' successfully.")

    def __del__(self) -> None:
        self.close()

    def create_books_table(self) -> None:
        with self.db_lock:
            with self.transaction:
                self.execute("""
                    PRAGMA encoding = "UTF-8";
                """)
                self.execute("""
                    Create Table "Books"(
                        Id           Integer            Primary Key                                    , -- 编号
                        Title        Text                              Not null                        , -- 标题
                        Author       Text                                          Default 'Unknown'   , -- 作者
                        Description  Text                                          Default ''          , -- 简介
                        Style        Text                                          Default 'Unknown'   , -- 风格
                        Cover        Blob                                          Default Null        , -- 封面
                        CoverFormat  Text                                          Default Null        , -- 封面格式
                        ChapterCount int                               Not Null                        , -- 章节数
                        Source       Text     Unique                   Not Null                        , -- 来源网址 格式: hostname+path,path不得以'/'结尾
                        Spider       Text                              Not NUll                        , -- 来源Spider
                        Status       int                                           Default 1           , -- 是否完结(1->完结 0->未完结)
                        PublishDate  Text                                          Default '0000-00-00', -- 发布日期 格式 %Y-%m-%d
                        UpdateDate   Text                                          Default '0000-00-00'  -- 更新日期 格式 %Y-%m-%d
                    );
                """)

    def check_primary_table_exist(self) -> None:
        with self.db_lock:
            try:
                res = self.query("Select 1 from Books;")
            except sqlite3.OperationalError:
                self.create_books_table()

            try:
                res = self.query("Select 1 from Chapters;")
            except sqlite3.OperationalError:
                self.create_chapters_table()

    def create_chapters_table(self) -> None:
        """
            为书籍创建章节表
        """
        self.execute(f"""
            Create Table Chapters(
                Id          Integer Primary Key Not Null, -- 编号
                BookId      int                 Not Null, -- 书籍编号
                ChapterId   int                         , -- 章节编号
                Title       Text                Not Null, -- 标题
                Content     Text                        , -- 内容
                Foreign Key (BookId) References Books(Id)  -- 外键约束
            );
        """)
        self.execute(
            "Create Unique Index Chapter_I on Chapters(BookId,ChapterId);")

    def insert_chapters(self, chapters: list[Chapter]) -> None:
        chapters_tuple_list = [i.to_tuple() for i in chapters]
        self.executemany(
            f"Insert into Chapters (BookId,ChapterId,Title,Content) Values (?,?,?,?);",
            chapters_tuple_list
        )

    def insert_chapter(self, chapter: Chapter) -> None:
        self.execute(
            f"Insert into Chapters (BookId,ChapterId,Title,Content) Values (?,?,?,?);",
            chapter.to_tuple()
        )

    def create_books(self, books: list[Book]) -> list[Book]:
        """
            创建图书并填充编号
        """
        # 先把Book 转成tuple方便executemany
        books_tuple_list = [i.to_tuple() for i in books]
        idx: int = 0

        with self.db_lock:  # 防止序号被扰乱
            idx = self.query("Select last_insert_rowid() from Books;")[0][0]
            self.executemany(
                """
                Insert into 'Books' (Title,Author,Description,Style,Cover,CoverFormat,ChapterCount,Source,Status,PublishDate,UpdateDate) Values (?,?,?,?,?,?,?,?,?,?,?,?);
                """,
                books_tuple_list
            )

        for i, book in enumerate(books):
            book.idx = i+idx+1
            book.update_book_index_to_chapters()

        return books

    def create_book(self, book: Book) -> Book:
        with self.db_lock:
            self.execute(
                """
                Insert into 'Books' (Title,Author,Description,Style,Cover,CoverFormat,ChapterCount,Source,Spider,Status,PublishDate,UpdateDate) Values (?,?,?,?,?,?,?,?,?,?,?,?);
                """,
                book.to_tuple()
            )

            idx = self.query("Select last_insert_rowid() from Books;")[0][0]
            book.idx = idx
            book.update_book_index_to_chapters()

        return book

    def is_book_exist(self, **params) -> bool:
        """
            判断满足条件的书籍是否存在
        """
        res = self.query_book_info(**params)
        return len(res) > 0

    def check_book_exist(self, **params) -> None:
        """
            断言书籍存在，否则抛出 `BookNotExistError` 异常
        """
        if not self.is_book_exist(**params):
            raise BookNotExistError()

    def is_chapter_exist(self, book_index: int, chapter_index: int) -> bool:
        """
            判断章节是否存在
        """
        if not self.is_book_exist(Id=book_index):
            raise BookNotExistError(Id=book_index)

        res = self.query(
            f"Select Id From Chapters Where BookId=={book_index} and ChapterId=={chapter_index};")
        return len(res) > 0

    def check_chapter_exist(self, book_index: int, chapter_index: int) -> None:
        """
            断言章节存在，否则抛出 `ChapterNotExistError` 异常
        """
        if not self.is_chapter_exist(book_index, chapter_index):
            raise ChapterNotExistError(book_index, chapter_index)

    def get_book_index(self, book: Book) -> int:
        self.check_book_exist(Source=book.source)
        res = self.query_book_info(Source=book.source)[0].idx
        book.idx = res
        book.update_book_index_to_chapters()
        return book.idx

    def update_book_single_info(self, book_index: int, item: str, value) -> None:
        """
            更新书籍单个信息
            e.g:
            ```
                db.update_book_single_info(1,"Title","Unknown")
            ```
        """
        if not self.is_book_exist(Id=book_index):
            raise BookNotExistError(Id=book_index)
        else:
            self.execute(
                f"Update Books Set {item}=? Where Id==?;",
                (value, book_index)
            )

    def update_book_info(self, book_index: int, **params) -> None:
        """
            更新书籍多个信息，使用不定参数指定。具体子段参见数据库定义
            e.g:
            ```
                db.update_book_info(1,Title="Unknown",Author="Unkown")
            ```
        """
        for k, v in params.items():
            self.update_book_single_info(book_index, k, v)

    def update_book_all_info(self, book: Book) -> None:
        """
            更新全部书籍信息，若该书籍不存在则创建
        """
        if not self.is_book_exist(Id=book.idx):
            self.create_book(book)

        self.execute(
            "Update Books Set Title=?,Author=?,Description=?,Style=?,Cover=?,CoverFormat=?,ChapterCount=?,Source=?,Spider=?,Status=?,PublishDate=?,UpdateDate=? Where Id == ?;",
            (book.title, book.author, book.desc, book.style, book.cover,
             book.cover_format, book.chapter_count, book.source, book.spider, book.status, datetime.strftime(book.publish, "%Y-%m-%d"), datetime.strftime(book.update, "%Y-%m-%d"), book.idx)
        )

    def update_chapter(self, chapter: Chapter) -> None:
        """
            更新章节信息
        """
        if not self.is_chapter_exist(chapter.book_index, chapter.chapter_index):
            raise ChapterNotExistError(
                chapter.book_index, chapter.chapter_index)

        self.execute(
            f"Update Chapters Set Title=?,Content=? Where BookId=? And ChapterId=?;",
            (chapter.title, chapter.content,
             chapter.book_index, chapter.chapter_index)
        )

    def delete_book(self, book_index: int) -> None:
        """
            删除书籍
        """
        self.check_book_exist(Id=book_index)
        self.execute(
            "Delete From Chapters Where BookId == ?;",
            (book_index,)
        )

        self.execute(
            "Delete From Books Where Id==?;",
            (book_index,)
        )

    def delete_chapter(self, book_index: int, chapter_index: int) -> None:
        """
            删除章节
        """
        if not self.is_chapter_exist(book_index, chapter_index):
            raise ChapterNotExistError(book_index, chapter_index)

        self.execute(
            f"Delete From Chapters where BookId=={book_index} and ChapterId=={chapter_index};"
        )

    @staticmethod
    def make_condition(**params):
        sql = "Where " if len(params) > 0 else ""

        for k, v in params.items():
            if type(v) == type(""):
                sql += f"{k} like '%{v}%' "
            elif type(v) == type(0):
                sql += f"{k} == {v} "
            else:
                raise UnsupportedType(v.__class__)

        return sql

    def query_book_info(self, limit=-1, offset=-1, **params) -> list[Book]:
        sql = "Select * From Books "
        sql += Database.make_condition(**params)
        if limit != -1:
            sql += f"Limit {limit} "
        if offset != -1:
            sql += f"Offset {offset} "
        sql += ";"

        res = self.query(sql)
        return [Book.from_tuple(i) for i in res]

    def query_chapter(self, book_index: int, chapter_index: int) -> Chapter:
        if not self.is_chapter_exist(book_index, chapter_index):
            raise ChapterNotExistError(book_index, chapter_index)

        res = self.query(
            f"Select BookId,ChapterId,Title,Content From Chapters Where BookId=={book_index} and ChapterId=={chapter_index};")

        return Chapter.from_tuple(res[0])

    def query_all_chapters(self, book_index: int) -> list[Chapter]:
        self.check_book_exist(Id=book_index)

        res = self.query(
            f"Select BookId,ChapterId,Title,Content From Chapters Where BookId=={book_index};")

        res = [Chapter.from_tuple(i) for i in res]
        res.sort()

        return res

    def begin_transaction(self):
        self.execute("Begin Transaction;")

    def commit_transaction(self):
        self.commit()
