from core.book_exporter import BookExpoter
from core.setting import *
from core.logger import Loggable
from core.book import *

from ebooklib import epub


class EpubExporter(BookExpoter):
    def __init__(self, setting_manager: SettingManager) -> None:
        super().__init__(setting_manager)

    async def export_book(self, book: Book, output: str):
        output = BookExpoter.fix_path(output, book.title, ".epub")

        out_book = epub.EpubBook()
        out_book.add_author(book.author)
        out_book.set_cover("cover"+book.cover_format, book.cover)
        out_book.set_title(book.title)

        html_items: list[epub.EpubHtml] = []
        for chapter in book.chapters:
            item = epub.EpubHtml(
                file_name=f'Chapter{chapter.chapter_index}.html', title=chapter.title)

            content: str = f"<h1>{chapter.title}</h1>\n"

            paras = [i.strip() for i in chapter.content.split('\n')]

            for para in paras:
                content += f"<p>{para}</p>\n"

            item.set_content(content)
            out_book.add_item(item)
            html_items.append(item)

        out_book.spine = html_items
        toc = []

        for i in html_items:
            toc.append(epub.Link(i.file_name, title=i.title, uid=i.file_name))
        out_book.toc = toc

        out_book.add_item(epub.EpubNav())
        out_book.add_item(epub.EpubNcx())

        epub.write_epub(output, out_book)
        self.log_info(f"Successfully export book '{book.title}' to '{output}'")
