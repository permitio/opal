class GitFailed(Exception):
    """an exception we throw on git failures that are caused by wrong
    assumptions.

    i.e: we want to track a non-existing branch, or git url is not valid.
    """

    def __init__(self, exc: Exception):
        self._original_exc = exc
        super().__init__()
