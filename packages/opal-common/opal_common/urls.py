from urllib.parse import ParseResult, parse_qsl, urlencode, urlparse, urlunparse


def set_url_query_param(url: str, param_name: str, param_value: str):
    """Given a url, set or replace a query parameter and return the modified
    url.

    >> set_url_query_param('https://api.permit.io/opal/data/config', 'token', 'secret')
    'https://api.permit.io/opal/data/config?token=secret'

    >> set_url_query_param('https://api.permit.io/opal/data/config&some=var', 'token', 'secret')
    'https://api.permit.io/opal/data/config&some=var?token=secret'
    """
    parsed_url: ParseResult = urlparse(url)

    query_params: dict = dict(parse_qsl(parsed_url.query))
    query_params[param_name] = param_value
    new_query_string = urlencode(query_params)

    return urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            new_query_string,
            parsed_url.fragment,
        )
    )
