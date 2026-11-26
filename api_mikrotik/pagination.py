"""Paginación de los listados de la API.

Los listados devuelven ``{"count": N, "next": ..., "previous": ...,
"results": [...]}`` con 100 elementos por página por defecto. Se puede pedir
otra página con ``?page=2`` y otro tamaño con ``?page_size=50`` (máximo 200).

La web (mikrotik_web) ya tolera esta forma: su ``get_list()`` lee la clave
``"results"``. Ojo: la web solo lee la primera página, así que con más de
100 registros en una lista la web no vería el resto; es el límite actual
y está documentado en ``docs/api.md``.
"""

from rest_framework.pagination import PageNumberPagination


class PaginacionAPI(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 200
