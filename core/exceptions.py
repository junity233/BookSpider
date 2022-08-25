from pyclbr import Function


class NonimplentException(Exception):
    class_: type
    func: Function

    def __init__(self, class_, func, *args: object) -> None:
        self.class_ = class_
        self.func = func
        Exception.__init__(self, class_, func, *args)

    def __str__(self) -> str:
        return f'Try to call nonimplent function "{self.func.__name__}" of "{self.class_.__name__}"'
