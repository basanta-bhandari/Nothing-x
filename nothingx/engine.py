import ctypes
import json
import os
from pathlib import Path
import sys

from .variants import backend_name


class Engine:
    def __init__(self, backend=None, path=None):
        self.backend = backend_name(backend)
        suffix = "dylib" if sys.platform == "darwin" else "so"
        library = Path(path or os.environ.get("NOTHINGX_ENGINE", Path(__file__).resolve().parent / f"bin/libnothingx_{self.backend}.{suffix}"))
        self.library = ctypes.CDLL(str(library))
        self.library.nx_engine_create.restype = ctypes.c_void_p
        self.library.nx_engine_destroy.argtypes = [ctypes.c_void_p]
        self.library.nx_engine_call.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.library.nx_engine_call.restype = ctypes.c_void_p
        self.library.nx_engine_free.argtypes = [ctypes.c_void_p]
        self.context = self.library.nx_engine_create()
        if not self.context:
            raise RuntimeError("Could not create the native backend.")
        from .models import MODELS
        self.call("configure", profiles=MODELS)

    def call(self, op, **values):
        request = json.dumps({"op": op, **values}, separators=(",", ":")).encode()
        pointer = self.library.nx_engine_call(self.context, request)
        if not pointer:
            raise MemoryError("Native backend allocation failed.")
        try:
            response = json.loads(ctypes.string_at(pointer))
        finally:
            self.library.nx_engine_free(pointer)
        if not response.get("ok"):
            raise ValueError(response.get("error", "Native backend rejected the request."))
        return response.get("result")

    def close(self):
        if self.context:
            self.library.nx_engine_destroy(self.context)
            self.context = None

    def __del__(self):
        if getattr(self, "context", None):
            self.close()
