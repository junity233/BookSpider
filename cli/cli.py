from asyncio.log import logger
from inspect import isfunction
from sys import version as python_version
import subprocess
import logging
import shlex


from .version import VERSION
from core.logger import Logger
from core.manager import Manager
from . import commands

logger = Logger("Console")

vaild_func = {}


@commands.command("Get help", "Name of the command")
def help(name: str = None):
    def get_declaration(func):
        msg = func.__name__+" "
        for i in func.__arg_commit__:
            msg += f'<{i[0]}> '
        return msg

    if name == None:
        print(f"Book Spider {VERSION} Manual\n")
        for func in vaild_func.values():
            print("%-25s : %s" %
                  (get_declaration(func), func.__command_commit__))
    else:
        func = None

        if name in vaild_func.keys():
            func = vaild_func[name]
        else:
            print(f"Command '{name}' is not found.")
            return

        print(f"Usage : {get_declaration(func)} \n")
        for arg in func.__arg_commit__:
            print(f"{arg[0]} : {arg[1]}")


def init(manager: Manager):
    for k, v in commands.__dict__.items():
        if isfunction(v) and ("__is_command__" in v.__dict__.keys() and v.__is_command__ == True):
            vaild_func[k] = v
    vaild_func["help"] = help
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
            command = shlex.split(input("> "))

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
        except SystemExit:
            manager.close()
            quit()
