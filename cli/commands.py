from core.manager import Manager
from core.logger import Logger
from prettytable import PrettyTable

from core.spider import Spider

"""
    Cli的命令模块
"""

mgr: Manager = None
logger = Logger("Console")


def command(commit, *args, **kargs):
    """
        为命令添加注释
    """
    def res(func):
        func.__command_commit__ = commit
        func.__is_command__ = True
        func.__arg_commit__ = []
        for idx, arg in enumerate(func.__code__.co_varnames):
            if idx >= len(args):
                if arg in kargs:
                    func.__arg_commit__.append(arg, kargs[arg])
            else:
                func.__arg_commit__.append((arg, args[idx]))
        return func

    return res


def call_func_by_op(func_table: dict[str], op: str, *params):
    if op in func_table.keys():
        func = func_table[op]
        func(*params)
    else:
        print("Unknown Operation.")


def args_to_kwargs(*args) -> dict[str, str]:
    kwargs = {}
    for i in args:
        if '=' in i:
            strs = i.split('=')
            kwargs[strs[0].strip()] = strs[1].strip()

    return kwargs


@command("Manager settings", "Operation", "The params of the operatrion.")
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


@command("Manager spiders", "Operation", "The params of the operatrion.")
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


@command("Managers Books", "Operation", "The params of the operatrion.")
def book(op: str, *params):
    def search(*params):
        kwargs = args_to_kwargs(*params)

        table = PrettyTable(
            ["Id", "Title", "Author", "Chapter Count", "Style", "Status", "Publish Date", "Update Date"])
        cnt = 0

        for book in mgr.query_book(**kwargs):
            table.add_row([book.idx, book.title, book.author, book.chapter_count, book.style,
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

    def export(index, outpath="."):
        try:
            index = int(index)
            mgr.export_book_by_id(index, outpath)
        except ValueError:
            if index == "all":
                mgr.export_all_book(outpath)
            else:
                logger.log_error("Invaild arguement")

    def remove(index):
        index = int(index)

        confirm = input("Confirm to remove book (Yes/No):")
        if confirm == "Yes":
            mgr.delete_book(index)

    func_table = {
        "search": search,
        "check": check,
        "export": export,
        "remove": remove
    }

    call_func_by_op(func_table, op, *params)


def select_spider(spiders: list[Spider]) -> Spider:
    print("Select a spider:")
    for idx, i in enumerate(spiders):
        print(f"    {idx}. {i.name}")
    print("")
    num = int(input("> (number) :"))

    if num < 0 or num > len(spiders):
        logger.log_error("Invaild number.")

    return spiders[num]


@command("Get book from url", "Thr url", "The params that pass to the spider.")
def get(url, *params):
    kwargs = args_to_kwargs(*params)
    vaild_spiders = mgr.get_vaild_spiders(url, **kwargs)
    if len(vaild_spiders) == 0:
        logger.log_error("No spider match the url!")
        return

    spider = select_spider(vaild_spiders)

    mgr.get_book(url, spider, **kwargs)


@command("Get all books in the specificed site.", "The params that pass to the spider")
def site(*params):
    spiders = list(mgr.spiders.values())
    if len(spiders) == 0:
        logger.log_error("No spider added.")
        return

    spider = select_spider(spiders)

    mgr.get_all_book(spider, **args_to_kwargs(*params))


@command("Run sql", "The sql")
def runsql(*params):
    sql = ""
    for i in params:
        sql += i+" "
    res = mgr.db.query(sql)
    table = PrettyTable()
    table.add_rows(res)
    print(table)


@command("Commit to the database.")
def commit():
    mgr.db.commit()


@command("Rollback database.")
def rollback():
    mgr.db.rollback()


@command("Exit")
def exit():
    quit()
