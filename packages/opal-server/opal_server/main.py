def create_app(*args, **kwargs):
    from opal_server.server import OpalServer

    server = OpalServer(*args, **kwargs)
    return server.app


app = create_app()
