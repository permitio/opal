from ..events import FetchEvent


# Callback signatures
async def OnFetchFailureCallback(exception: Exception, event: FetchEvent):
    """
    Args:
        exception (Exception): The exception thrown causing the failure
        event (FetchEvent): the queued event which failed
    """
    pass
