from core.book_exporter import BookExpoter
from core.setting import SettingManager
from core.book import Book
import aiofiles


class TextExporter(BookExpoter):
    """
        导出为纯文本
    """

    def __init__(self, setting_manager: SettingManager) -> None:
        super().__init__(setting_manager)

    async def export_book(self, book: Book, output: str):
        output = TextExporter.fix_path(output, book.title, ".txt")
        async with aiofiles.open(output, "w", encoding="utf-8") as f:
            texts = []
            texts.append(book.title+"\n\n")
            texts.append(book.desc + "\n\n")

            for chapter in book.chapters:
                texts.append(chapter.title+"\n")
                texts.append(chapter.content+"\n")

            await f.write(str.join('',texts))

        async with aiofiles.open(output+book.cover_format, "wb") as f:
            await f.write(book.cover)
        self.log_info(f"Successfully export book '{book.title}' to {output}")
