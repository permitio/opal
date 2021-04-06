from urllib.parse import urlparse, urlunparse, urlencode, parse_qsl, ParseResult

def set_url_query_param(url: str, param_name: str, param_value: str):
    """
    Given a url, set or replace a query parameter and return the modified url.

    >> set_url_query_param('https://api.authorizon.com/opal/data/config', 'token', 'secret')
    'https://api.authorizon.com/opal/data/config?token=secret'

    >> set_url_query_param('https://api.authorizon.com/opal/data/config&some=var', 'token', 'secret')
    'https://api.authorizon.com/opal/data/config&some=var?token=secret'
    """
    parsed_url: ParseResult = urlparse(url)

    query_params: dict = dict(parse_qsl(parsed_url.query))
    query_params[param_name] = param_value
    new_query_string = urlencode(query_params)

    return urlunparse((
        parsed_url.scheme,
        parsed_url.netloc,
        parsed_url.path,
        parsed_url.params,
        new_query_string,
        parsed_url.fragment,
    ))