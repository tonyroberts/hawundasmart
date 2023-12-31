from contextlib import asynccontextmanager
import functools
import aiohttp
import asyncio
import weakref
import socket


class ResponseHandler(aiohttp.client_proto.ResponseHandler):
    """Patched ResponseHandler that calls socket.shutdown
    when the connection is closed.

    The wundasmart hub will becomes unresponsive after a lot of
    requests and my current theory is that aiohttp is not sending
    the TCP FIN message after getting a response with the
    'Connection: close' header.

    See https://github.com/aio-libs/aiohttp/issues/4685
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__closed_transport = None

    def close(self):
        self.__closed_transport = weakref.ref(self.transport)
        super().close()

    def connection_lost(self, exc):
        super().connection_lost(exc)

        transport = None
        if self.__closed_transport is not None:
            transport = self.__closed_transport()
            self.__closed_transport = None

        if transport is not None:
            if hasattr(transport._sock, 'shutdown') and transport._sock.fileno() != -1:
                transport._sock.shutdown(socket.SHUT_RDWR)


class TCPConnector(aiohttp.TCPConnector):
    """Patched TCPConnector to use our patched ResponseHandler above.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._factory = functools.partial(ResponseHandler, loop=self._loop)


@asynccontextmanager
async def get_session():
    connector = TCPConnector(force_close=True, limit=1)
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            yield session
    finally:
        await connector.close()
        # Zero-sleep to allow underlying connections to close
        # https://docs.aiohttp.org/en/stable/client_advanced.html#graceful-shutdown
        await asyncio.sleep(0)
