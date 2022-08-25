from core.manager import Manager
from core.logger import Logger
from prettytable import PrettyTable

from core.spider import Spider

"""
    Cli的命令模块
    在此模块内定义的所有方法都将被视为命令,除非使用not_command修饰
"""

mgr: Manager = None
logger = Logger("Console")


def not_command(func):
    """
        非命令方法的修饰符
    """
    func.__not_command__ = True
    return func


not_command.__not_command__ = True


@not_command
def call_func_by_op(func_table: dict[str], op: str, *params):
    if op in func_table.keys():
        func = func_table[op]
        func(*params)
    else:
        print("Unknown Operation.")


@not_command
def args_to_kwargs(*args) -> dict[str, str]:
    kwargs = {}
    for i in args:
        if '=' in i:
            strs = i.split('=')
            kwargs[strs[0].strip()] = strs[1].strip()

    return kwargs


def setting(op, *params):
    setmgr = mgr.setting_manager

    def print_value(k, v):
        print(f"key = '{k}' ,value = {v} ,type = {v.__class__.__name__}")

    def set_setting(field, name, value, type_="str"):
        if type_ == "int":
            value = int(value)
        elif type_ == "bool":
            value = bool(value)

        setmgr.set(field, name, value)

    def get_setting(field, key):
        if setmgr.has_key(field, key):
            v = setmgr.get(field, key)
            print_value(key, v)
        else:
            logger.log_error(f"Key '{key}' of field '{field}' not found!")

    def remove_setting(field, key):
        if setmgr.has_key(field, key):
            setmgr.remove_key(field, key)
        else:
            logger.log_error(f"Key '{key}' of field '{field}' not found!")

    def list_setting(field):
        setmgr.check_field_exist(field)
        for k, v in setmgr.get_field(field).items():
            print_value(k, v)

    def list_fields():
        for field in setmgr.get_field_names():
            print(field)

    def help():
        print(
            "Usage : setting set/get/remove/list/fields [field] [key] [value]\n")

    func_table = {
        "set": set_setting,
        "get": get_setting,
        "remove": remove_setting,
        "list": list_setting,
        "fields": list_fields,
        "help": help
    }

    call_func_by_op(func_table, op, *params)


def spider(op: str, *params):
    def add_spider(name: str):
        mgr.add_spider(name)

    def remove_spider(name: str):
        mgr.remove_spider(name)

    def list_spiders():
        for name in mgr.spiders.keys():
            print(name)

    def help():
        print("Usage : spider add/remove/list [name]")

    func_table = {
        "add": add_spider,
        "remove": remove_spider,
        "list": list_spiders,
        "help": help
    }
    call_func_by_op(func_table, op, *params)


def book(op: str, *params):
    def search(*params):
        kwargs = args_to_kwargs(*params)

        table = PrettyTable(
            ["Id", "Title", "Author", "Status", "Publish Date", "Update Date"])
        cnt = 0

        for book in mgr.query_book(**kwargs):
            table.add_row([book.idx, book.title, book.author,
                          "End" if book.status else "Not End", book.publish, book.update])
            cnt += 1

        print(f"{cnt} result in tot.\n")
        print(table)

    def check(index="", *params):
        if index == "":
            mgr.check_all_book()
        else:
            index = int(index)
            mgr.check_book(index, *params)

    def export(index, outpath=""):
        index = int(index)
        mgr.export_book(index, outpath)

    def remove(index):
        index = int(index)

        confirm = input("Confirm to remove book (Yes/No):")
        if confirm == "Yes":
            mgr.delete_book(index)

    def list_(cnt, offset):
        cnt = int(cnt)
        offset = int(offset)
        search(Limit=cnt, Offset=offset)

    func_table = {
        "search": search,
        "check": check,
        "export": export,
        "remove": remove,
        "list": list_
    }

    call_func_by_op(func_table, op, *params)


@not_command
def select_spider(spiders: list[Spider]) -> Spider:
    print("Select a spider:")
    for idx, i in enumerate(spiders):
        print(f"    {idx}. {i.name}")
    print("")
    num = int(input("> (number) :"))

    if num < 0 or num > len(spiders):
        logger.log_error("Invaild number.")

    return spiders[num]


def get(url, *params):
    kwargs = args_to_kwargs(params)
    vaild_spiders = mgr.get_vaild_spiders(url, **kwargs)
    if len(vaild_spiders) == 0:
        logger.log_error("No spider match the url!")
        return

    spider = select_spider(vaild_spiders)

    mgr.get_book(url, spider, **kwargs)


def site(*params):
    spiders = list(mgr.spiders.values())
    if len(spiders) == 0:
        logger.log_error("No spider added.")
        return

    spider = select_spider(spiders)

    mgr.get_all_book(spider, **args_to_kwargs(*params))


def commit():
    mgr.db.commit()


def rollback():
    mgr.db.rollback()


def help():
    print("Book Spider Manual\n")
    print("setting              | Access setting.")
    print("book                 | Manage books")
    print("spider               | Manage spiders")
    print("commit               | Commit to database")
    print("rollback             | Rollback to database")
    print("get <url>            | Get book")
    print("site                 | Get all book")
    print("")
