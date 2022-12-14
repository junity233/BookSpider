from core.spider import Spider
from core.setting import SettingManager
from core.book import Book, Chapter
from typing import Any, Iterable
from lxml.etree import Element
from urllib.parse import urljoin
from core.utils import convert_url


class BQGSpider(Spider):
    name = "BQGSpider"

    def __init__(self, setting_manager: SettingManager) -> None:
        super().__init__(setting_manager)

    @staticmethod
    def check_url(url: str, **params) -> bool:
        url = convert_url(url)
        return url.startswith('www.xbiquge.so')

    async def get_book_info(self, book: Book, **params) -> tuple[Book, Any]:
        html = await self.async_get_html(book.whole_url)
        book.title = html.xpath(r'//*[@id="info"]/h1/text()')[0]
        book.author = html.xpath(r'//*[@id="info"]/p[1]/a/text()')[0]
        book.desc = Spider.get_ele_content(html.xpath(r'//*[@id="intro"]')[0])
        book.cover, book.cover_format = await self.async_get_image(
            html.xpath(r'//*[@id="fmimg"]/img/@src')[0])
        book.update = Spider.match_date(
            html.xpath(r'//*[@id="info"]/p[3]/text()')[0])
        book.status = html.xpath(r'//*[@id="fmimg"]/span/@class')[0] == 'a'
        book.style = html.xpath(r'/html/body/div[2]/div[1]/text()')[0][3:5]

        dl = html.xpath(r'//*[@id="list"]/dl')[0]
        center = html.xpath(r'//*[@id="list"]/dl/center')[0]

        idx = dl.index(center)+2

        chapters = []
        cnt = 1

        for i in range(idx, len(dl)):
            dd = dl[i]
            a = dd.xpath("./a")
            if len(a) == 0:
                continue
            a = a[0]

            chapter_title = a.text
            chapter_url = urljoin(book.whole_url+'/', a.attrib["href"])
            chapters.append((chapter_title, chapter_url, cnt))
            cnt += 1

        return book, chapters

    async def get_book_menu(self, data: list[tuple[str, str, int]], **params) -> Iterable[tuple[int, Any]]:
        return [(i[2], i) for i in data]

    async def get_chapter_content(self, chapter: Chapter, data: Any, silent=False, **params) -> Chapter:
        chapter.title = data[0]

        html = await self.async_get_html(data[1])

        content = html.xpath(r'//*[@id="content"]')[0]
        content.text = ""

        chapter.content = Spider.get_ele_content(content)

        if not silent:
            self.log_info(f"Get chapter '{chapter.title}' successfully.")

        return chapter

    def get_all_book(self, start=1, end=-1, **param) -> Iterable[Book]:
        html = self.get_html(r'https://www.xbiquge.so/top/toptime/1.html')
        pagenum = int(html.xpath(
            r'//*[@id="pagestats"]//text()')[0].split('/')[1])

        if start != 1:
            start = int(start)

        if end != -1:
            end = int(end)
        else:
            end = pagenum

        for i in range(start, end+1):
            html = self.get_html(
                f'https://www.xbiquge.so/top/toptime/{i}.html')
            lis = html.xpath(r'//*[@id="main"]/div[1]/li')
            self.set_setting("max_page", i)

            for j in lis:
                a = j.xpath('./span[@class="s2"]/a')[0]
                title = a.text
                source = a.attrib["href"]

                yield self.make_book(title=title, source=source)
