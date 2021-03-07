from aiohttp_requests import Requests
import aiohttp

class AioRequests(Requests):

    @property
    def session(self):
        """ An instance of aiohttp.ClientSession """
        # fix DeprecationWarning: client.loop property is deprecated
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(*self._session_args[0], **self._session_args[1])
        return self._session

requests = AioRequests()