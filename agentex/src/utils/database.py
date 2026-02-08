from urllib.parse import urlparse

import asyncpg


def adjust_db_url(url):
    url_parts = urlparse(url)
    url_parts = url_parts._replace(scheme="postgresql")  # noqa
    return url_parts.geturl()


def async_db_engine_creator(url):
    def creator():
        url_to_connect = adjust_db_url(url)
        return asyncpg.connect(url_to_connect)

    return creator
