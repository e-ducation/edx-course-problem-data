from __future__ import unicode_literals

from rest_framework.pagination import PageNumberPagination


class BlockNumberPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
