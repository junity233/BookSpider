from RainbowPrint import RainbowPrint as RP
from datetime import datetime
from threading import Lock

LogGrade = 1


def make_msg(type_, who, msg) -> str:
    t = datetime.strftime(datetime.now(), "%Y-%m-%d %H:%M:%S")
    return f"{t} [{type_}] <{who}> : {msg}"


log_lock = Lock()


class Loggable:
    def log_debug(self, msg):
        with log_lock:
            RP.rainbow_debug(make_msg("Debug", self.__class__.__name__, msg))

    def log_info(self, msg):
        with log_lock:
            RP.rainbow_info(make_msg("Info", self.__class__.__name__, msg))

    def log_error(self, msg):
        with log_lock:
            RP.rainbow_error(make_msg("Error", self.__class__.__name__, msg))


class Logger:
    name: str

    def __init__(self, name: str) -> None:
        self.name = name

    def log_debug(self, msg):
        with log_lock:
            RP.rainbow_debug(make_msg("Debug", self.name, msg))

    def log_info(self, msg):
        with log_lock:
            RP.rainbow_info(make_msg("Info", self.name, msg))

    def log_error(self, msg):
        with log_lock:
            RP.rainbow_error(make_msg("Error", self.name, msg))
