from asyncio.log import logger
from inspect import isfunction
from sys import version as python_version
import subprocess
import logging


from .version import VERSION
from core.logger import Logger
from core.manager import Manager
from . import commands

logger = Logger("Console")

vaild_func = {
    "quit": lambda: quit(),
    "exit": lambda: exit(),
    "credis": lambda: credits()
}


def init(manager: Manager):
    for k, v in commands.__dict__.items():
        if isfunction(v) and ("__not_command__" not in v.__dict__.keys() or v.__not_command__ == False):
            vaild_func[k] = v
    commands.mgr = manager


def shell(*params):
    cmd = ""

    for i in params:
        cmd += i+" "

    subprocess.call(["cmd.exe", "/c", cmd])


def print_exception(e: Exception):
    logging.exception(e)


def run_function_protected(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except KeyboardInterrupt:
        return
    except Exception as e:
        logger.log_error(f"{e.__class__.__name__} :")
        print_exception(e)


def cli_main(manager: Manager):
    print(f"Book Spider System {VERSION} on Python ({python_version})")
    print(f"Type 'quit' or 'exit' to exit,or 'help' to get more infomation.\n")

    init(manager)

    while True:
        try:
            command = input("> ").split(" ")
            if " " in command:
                command.remove(" ")

            if len(command) == 0:
                continue

            if command[0].startswith("@"):
                command[0] = command[0][1:]
                run_function_protected(shell, *command)
                continue

            if command[0] not in vaild_func:
                logger.log_error("Command not found")
                continue

            func = vaild_func[command[0]]
            run_function_protected(func, *command[1:])

        except KeyboardInterrupt:
            print("")
            continue
