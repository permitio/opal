
import debugpy
#debugpy.listen(("0.0.0.0", 5678))
print("Waiting for debugger attach...")
#debugpy.wait_for_client()  # Optional, wait for debugger to attach before continuing

def create_app(*args, **kwargs):
    from opal_server.server import OpalServer

    server = OpalServer(*args, **kwargs)
    return server.app


app = create_app()
