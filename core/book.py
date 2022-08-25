from datetime import datetime


class Chapter:
    book_index: int  # 书籍编号
    chapter_index: int  # 章节序号
    title: str  # 标题
    content: str  # 内容

    def __init__(self, book_index, chapter_index, title, content) -> None:
        self.book_index = book_index
        self.chapter_index = chapter_index
        self.title = title
        self.content = content

    def __lt__(self, s):
        return self.chapter_index < s.chapter_index

    def to_tuple(self) -> tuple[3]:
        """
            转为元组，数据库插入时使用
        """
        return (self.book_index, self.chapter_index,  self.title, self.content)

    @staticmethod
    def from_tuple(data):
        return Chapter(
            book_index=data[0],
            chapter_index=data[1],
            title=data[2],
            content=data[3]
        )


class Book:
    idx: int  # 书籍编号
    title: str  # 书籍标题
    author: str  # 作者
    chapter_count: int  # 章节数
    source: str  # 来源Url
    spider: str  # 来源Spider
    desc: str  # 简介
    style: str  # 风格（玄幻/修仙...）
    cover: bytes  # 封面图
    cover_format: str  # 封面图格式
    status: bool  # 是否完结
    update: datetime  # 更新时间
    publish: datetime  # 发布时间
    chapters: list[Chapter]  # 章节列表

    def __init__(self, title="", author="", source="", spider="", desc="", style="", idx=-1, chapter_count=0, cover=None, cover_format=None, status=True, update=datetime(1970, 1, 1), publish=datetime(1970, 1, 1)) -> None:
        self.title = title
        self.author = author
        self.source = source
        self.desc = desc
        self.style = style
        self.update = update
        self.publish = publish
        self.cover = cover
        self.cover_format = cover_format
        self.idx = idx
        self.chapter_count = chapter_count
        self.chapters = []
        self.status = status
        self.spider = spider
        pass

    def to_tuple(self):
        return (
            self.title,
            self.author,
            self.desc,
            self.style,
            self.cover,
            self.cover_format,
            self.chapter_count,
            self.source,
            self.spider,
            int(self.status),
            datetime.strftime(self.publish, "%Y-%m-%d"),
            datetime.strftime(self.update, "%Y-%m-%d")
        )

    @staticmethod
    def from_tuple(data):
        return Book(
            idx=data[0],
            title=data[1],
            author=data[2],
            desc=data[3],
            style=data[4],
            cover=data[5],
            cover_format=data[6],
            chapter_count=data[7],
            source=data[8],
            spider=data[9],
            status=bool(data[10]),
            publish=datetime.strptime(data[11], "%Y-%m-%d"),
            update=datetime.strptime(data[12], "%Y-%m-%d")
        )

    def add_chapter(self, title, content, idx=-1) -> Chapter:
        """
            添加章节到书籍中，可用于插入章节
        """
        if idx == -1:
            idx = self.chapter_count+1
            self.chapter_count += 1

        chapter = Chapter(self.idx, idx, title, content)
        self.chapters.append(chapter)
        return chapter

    def make_chapter(self, idx) -> Chapter:
        """
            通过`idx`创建章节，可用于修改
        """
        chapter = Chapter(self.idx, idx, None, None)
        return chapter

    def update_book_index_to_chapters(self) -> None:
        for chapter in self.chapters:
            chapter.book_index = self.idx

    def __str__(self) -> str:
        return f'<Book {self.idx} "{self.title}" by "{self.author}">'
