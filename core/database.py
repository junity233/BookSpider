from datetime import datetime
import sqlite3
from threading import RLock

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
        Loggable.__init__(self)

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
                        Id           Integer            Primary Key                                    , -- ??????
                        Title        Text                              Not null                        , -- ??????
                        Author       Text                                          Default 'Unknown'   , -- ??????
                        Description  Text                                          Default ''          , -- ??????
                        Style        Text                                          Default 'Unknown'   , -- ??????
                        Cover        Blob                                          Default Null        , -- ??????
                        CoverFormat  Text                                          Default Null        , -- ????????????
                        ChapterCount int                               Not Null                        , -- ?????????
                        Source       Text     Unique                   Not Null                        , -- ???????????? ??????: hostname+path,path?????????'/'??????
                        Spider       Text                              Not NUll                        , -- ??????Spider
                        Status       int                                           Default 1           , -- ????????????(1->?????? 0->?????????)
                        PublishDate  Text                                          Default '0000-00-00', -- ???????????? ?????? %Y-%m-%d
                        UpdateDate   Text                                          Default '0000-00-00'  -- ???????????? ?????? %Y-%m-%d
                    );
                """)

    def check_primary_table_exist(self) -> None:
        with self.db_lock:
            try:
                self.execute("Select 1 from Books;")
            except sqlite3.OperationalError:
                self.create_books_table()

            try:
                self.execute("Select 1 from Chapters;")
            except sqlite3.OperationalError:
                self.create_chapters_table()

    def create_chapters_table(self) -> None:
        """
            ????????????????????????
        """
        self.execute(f"""
            Create Table Chapters(
                Id          Integer Primary Key Not Null, -- ??????
                BookId      int                 Not Null, -- ????????????
                ChapterId   int                         , -- ????????????
                Title       Text                Not Null, -- ??????
                Content     Text                        , -- ??????
                Foreign Key (BookId) References Books(Id)  -- ????????????
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
            ???????????????????????????
        """
        # ??????Book ??????tuple??????executemany
        books_tuple_list = [i.to_tuple() for i in books]
        idx: int = 0

        with self.db_lock:  # ?????????????????????
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

    def is_book_exist(self, *params, **kparams) -> bool:
        """
            ???????????????????????????????????????
        """
        res = self.query_book_info(*params, **kparams)
        return len(res) > 0

    def check_book_exist(self, **params) -> None:
        """
            ????????????????????????????????? `BookNotExistError` ??????
        """
        if not self.is_book_exist(**params):
            raise BookNotExistError()

    def is_chapter_exist(self, book_index: int, chapter_index: int) -> bool:
        """
            ????????????????????????
        """
        if not self.is_book_exist(Id=book_index):
            raise BookNotExistError(Id=book_index)

        res = self.query(
            f"Select Id From Chapters Where BookId=={book_index} and ChapterId=={chapter_index};")
        return len(res) > 0

    def check_chapter_exist(self, book_index: int, chapter_index: int) -> None:
        """
            ????????????????????????????????? `ChapterNotExistError` ??????
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
            ????????????????????????
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
            ???????????????????????????????????????????????????????????????????????????????????????
            e.g:
            ```
                db.update_book_info(1,Title="Unknown",Author="Unkown")
            ```
        """
        for k, v in params.items():
            self.update_book_single_info(book_index, k, v)

    def update_book_all_info(self, book: Book) -> None:
        """
            ?????????????????????????????????????????????????????????
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
            ??????????????????
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
            ????????????
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
            ????????????
        """
        if not self.is_chapter_exist(book_index, chapter_index):
            raise ChapterNotExistError(book_index, chapter_index)

        self.execute(
            f"Delete From Chapters where BookId=={book_index} and ChapterId=={chapter_index};"
        )

    @staticmethod
    def make_condition(*params, **kparams):
        sql = "Where " if len(kparams) + len(params) > 0 else ""
        flag = False

        for k, v in kparams.items():
            if flag:
                sql += "and "
            else:
                flag = True
            if type(v) == type(""):
                sql += f"{k} == '{v}' "
            elif type(v) == type(0):
                sql += f"{k} == {v} "
            else:
                raise UnsupportedType(v.__class__)

        for i in params:
            if flag:
                sql += "and "+i
            else:
                sql += i
                flag = True

        return sql

    def query_book_info(self, limit=-1, offset=-1, *params, **kparams) -> list[Book]:
        sql = "Select * From Books "
        sql += Database.make_condition(*params, **kparams)
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
