from __future__ import annotations

import re
import asyncio

from zlib import compress
from typing import Optional, Union

from aiohttp import ClientSession

from .response import TioResponse
from .exceptions import ApiError, LanguageNotFound


class Tio:

    def __init__(
        self, 
        session: Optional[ClientSession] = None, 
        loop: Optional[asyncio.AbstractEventLoop] = None, *,
        store_languages: Optional[bool] = True,
    ) -> None:

        self._store_languages = store_languages
        self.API_URL       = "https://tio.run/cgi-bin/run/api/"
        self.LANGUAGES_URL = "https://tio.run/languages.json"
        self.languages = []

        if loop:
            self.loop = loop
        else:
            try:
                self.loop = asyncio.get_running_loop()
            except RuntimeError:
                self.loop = asyncio.get_event_loop()
        
        if session:
            self.session = session
        else:
            self.session = None

        if self.loop.is_running():
            self.loop.create_task(self._initialize())
        else:
            self.loop.run_until_complete(self._initialize())
        
        return None

    async def __aenter__(self) -> Tio:
        await self._initialize()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    async def close(self) -> None:
        await self.session.close()

    async def _initialize(self) -> None:
        self.session = ClientSession()
        if self._store_languages:
            async with self.session.get(self.LANGUAGES_URL) as r:
                if r.ok:
                    data = await r.json()
                    self.languages = list(data.keys())
        return None

    def _format_payload(self, name: str, obj: Union[list, str]) -> bytes:
        if not obj:
            return b''
        elif isinstance(obj, list):
            content = ['V' + name, str(len(obj))] + obj
            return bytes('\x00'.join(content) + '\x00', encoding='utf-8')
        else:
            return bytes(
                f"F{name}\x00{len(bytes(obj, encoding='utf-8'))}\x00{obj}\x00", 
                encoding='utf-8'
            )
    
    async def execute(
        self, code: str, *, 
        language  : str, 
        inputs    : Optional[str] = "",
        compiler_flags: Optional[list] = [], 
        Cl_options: Optional[list] = [], 
        arguments : Optional[list] = [], 
    ) -> Optional[TioResponse]:

        if language not in self.languages:
            match = [l for l in self.languages if language in l]
            if match:
                language = match[0]

        data = {
            "lang"       : [language],
            ".code.tio"  : code,
            ".input.tio" : inputs,
            "TIO_CFLAGS" : compiler_flags,
            "TIO_OPTIONS": Cl_options,
            "args"       : arguments,
        }

        bytes_ = b''.join(
            map(self._format_payload, data.keys(), data.values())
        ) + b'R'

        data = compress(bytes_, 9)[2:-4]

        async with self.session.post(self.API_URL, data=data) as r:

            if r.ok:
                data = await r.read()
                data = data.decode("utf-8")

                if re.search(r"The language ?'.+' ?could not be found on the server.", data):
                    raise LanguageNotFound(data[16:])
                else:
                    return TioResponse(data, language)
            else:
                raise ApiError(f"Error {r.status}, {r.reason}")