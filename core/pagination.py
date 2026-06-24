from rest_framework.pagination import PageNumberPagination


class FlexiblePagination(PageNumberPagination):
    """Allow clients to set page_size via query param, capped at 500."""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 500
