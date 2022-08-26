from urllib.parse import urlparse
from datetime import datetime


def convert_url(url):
    """
        去除Url中无关的部分,仅保留hostname和path部分
    """
    url_parsed = urlparse(url)
    try:
        url: str = url_parsed.hostname+url_parsed.path
        if url.endswith('/'):
            url = url[:-1]
    except TypeError:
        pass
    return url


def str_to_date(s):
    formats = ["%Y-%m-%d", "%Y/%m/%d",
               "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"]

    for i in formats:
        try:
            return datetime.strptime(s, i)
        except ValueError:
            continue
    raise ValueError(f"{s} is not a date!")
