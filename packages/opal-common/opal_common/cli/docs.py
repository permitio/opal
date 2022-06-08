class MainTexts:
    def __init__(self, first_line, name):

        self.header = f"""\b
    {first_line}
    Open-Policy Administration Layer - {name}\b\f"""

        self.docs = f"""\b
    Config top level options:
        - Use env-vars (same as cmd options) but uppercase
            and with "_" instead of "-"; all prefixed with "OPAL_"
        - Use command line options as detailed by '--help'
        - Use .env or .ini files

    \b
    Examples:
        - opal-{name} --help                           Detailed help on CLI
        - opal-{name} run --help                       Help on run command
        - opal-{name} run --engine-type gunicorn       Run {name} with gunicorn
    \b
    """
