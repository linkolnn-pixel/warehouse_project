from urllib.parse import urlencode, urlsplit

from django.http import QueryDict
from django.urls import Resolver404, resolve
from django.utils.http import url_has_allowed_host_and_scheme


def return_destination(request, fallback, *allowed_routes):
    destination = request.GET.get("return_to", "")
    if not destination.startswith("/") or not url_has_allowed_host_and_scheme(destination, allowed_hosts=set()):
        return fallback

    try:
        route = resolve(urlsplit(destination).path).url_name
    except Resolver404:
        return fallback

    return destination if route in allowed_routes else fallback


def url_with_return(destination, return_to):
    return destination + "?" + urlencode({"return_to": return_to})


def with_query_parameter(destination, name, value):
    parts = urlsplit(destination)
    query = QueryDict(parts.query, mutable=True)
    query[name] = str(value)
    return parts._replace(query=query.urlencode()).geturl()
