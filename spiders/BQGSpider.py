from core.spider import Spider
from core.setting import SettingManager
from core.book import Book, Chapter
from typing import Any, Iterable
from lxml.etree import Element
from urllib.parse import urljoin


class BQGSpider(Spider):
    name = "BQGSpider"

    def __init__(self, setting_manager: SettingManager) -> None:
        super().__init__(setting_manager)

    def check_url(self, url: str, **params) -> bool:
        return url.startswith('https://www.xbiquge.so/') or url.startswith('http://www.xbiquge.so/')

    def get_book_info(self, book: Book, url: str, **params) -> tuple[Book, Any]:
        html = self.get_html(url)
        book.title = html.xpath(r'//*[@id="info"]/h1/text()')[0]
        book.author = html.xpath(r'//*[@id="info"]/p[1]/a/text()')[0]
        book.desc = Spider.get_ele_content(html.xpath(r'//*[@id="intro"]')[0])
        book.cover, book.cover_format = self.get_image(
            html.xpath(r'//*[@id="fmimg"]/img/@src')[0])
        book.update = Spider.match_date(
            html.xpath(r'//*[@id="info"]/p[3]/text()')[0])
        book.status = html.xpath(r'//*[@id="fmimg"]/span/@class')[0] == 'a'
        book.style = html.xpath(r'/html/body/div[2]/div[1]/text()')[0][3:5]

        dl = html.xpath(r'//*[@id="list"]/dl')[0]
        center = html.xpath(r'//*[@id="list"]/dl/center')[0]

        idx = dl.index(center)+2

        chapters = []

        for i in range(idx, len(dl)):
            dd = dl[i]
            a = dd.xpath("./a")
            if len(a) == 0:
                continue
            a = a[0]

            chapter_title = a.text
            chapter_url = urljoin(url, a.attrib["href"])
            chapters.append((chapter_title, chapter_url, i-idx+1))

        return book, chapters

    def get_book_menu(self, data: list[tuple[str, str, int]], **params) -> Iterable[tuple[int, Any]]:
        for i in data:
            yield i[2], i

    def get_chapter_content(self, chapter: Chapter, data: Any, **params) -> Chapter:
        chapter.title = data[0]

        html = self.get_html(data[1])

        content = html.xpath(r'//*[@id="content"]')[0]
        content.text = ""

        chapter.content = Spider.get_ele_content(content)

        self.log_info(f"Get chapter {chapter.title} successfully.")

        return chapter
