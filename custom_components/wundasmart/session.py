from contextlib import asynccontextmanager
from typing import AsyncGenerator
import functools
import aiohttp
import asyncio
import weakref
import socket

# Minimum keepalive timeout for persistent session connections
MIN_KEEPALIVE_TIMEOUT = 300

# Limit the number of sessions that can be in use at any one time
_semaphores = {}

# Persistent sessions by ip address
_sessions = {}

def _get_semaphore(wunda_ip):
    """Return a semaphore object to restrict making concurrent requests to the Wundasmart hub switch."""
    semaphore = _semaphores.get(wunda_ip)
    if semaphore is None:
        semaphore = asyncio.Semaphore(value=1)
        _semaphores[wunda_ip] = semaphore
    return semaphore


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
        if self.transport is not None:
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
async def get_persistent_session(wunda_ip, keepalive_timeout) -> AsyncGenerator[aiohttp.ClientSession]:
    """Returns an existing persistent session, if there is one and it
    isn't closed. If there isn't one, a new one is created with the
    keepalive timeout set."""
    async with _get_semaphore(wunda_ip):
        session = _sessions.get(wunda_ip)
        if not session or session.closed:
            connector = TCPConnector(force_close=False,
                                     limit=1,
                                     keepalive_timeout=max(keepalive_timeout, MIN_KEEPALIVE_TIMEOUT),
                                     enable_cleanup_closed=True)
            session = aiohttp.ClientSession(connector=connector)
        _sessions[wunda_ip] = session
        yield session


@asynccontextmanager
async def get_transient_session(wunda_ip) -> AsyncGenerator[aiohttp.ClientSession]:
    """Session manager for a new session that gets closed when exiting the context manager."""
    async with _get_semaphore(wunda_ip):
        connector = TCPConnector(force_close=True, limit=1)
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                yield session
        finally:
            await connector.close()
            # Zero-sleep to allow underlying connections to close
            # https://docs.aiohttp.org/en/stable/client_advanced.html#graceful-shutdown
            await asyncio.sleep(0)
