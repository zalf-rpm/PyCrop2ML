# coding: utf8
from pycropml.transpiler.rules.generalRule import GeneralRule
from pycropml.transpiler.pseudo_tree import Node


def translateNotContains(node):
    return Node("simpleCall", op='not in', value=node.args, sequence=node.receiver, pseudo_type='Boolean')

def translateDictkeys(node): return Node("method_call", receiver=node.receiver, message=".keys()", args=[], pseudo_type=node.pseudo_type)
def translatePrint(node): return Node(type="ExprStatNode", expr=Node(type="call", function="print", args=node.args))
def translateModulo(node): return Node(type="binary_op", op="%", left=node.args[0], right=node.args[1])

def translateCopy(node):
    return Node(type="call", function = "copy", args=[Node("local", name=node.args.name)])

def translateIntegr(node):
    pass

class PythonRules(GeneralRule):

    def __init__(self):
        GeneralRule.__init__(self)

    binary_op = {"and": "and",
                 "or": "or",
                 "not": "not",
                 "<": "<",
                 ">": ">",
                 "==": "==",
                 "+": "+",
                 "-": "-",
                 "*": "*",
                 "/": "/",
                 ">=": ">=",
                 "<=": "<=",
                 "!=": "!=",
                 "%":"%",
                 "is_not":"is not",
                 "is":"is"
                 }

    unary_op = {
        'not': 'not ',
        '+': '+',
        '-': '-',
        '~': '~'
    }

    types = {
        "int": "int",
        "float": "float",
        "bool": "bool",
        "list": "list",
        "tuple": "tuple",
        "str": "str",
        "dict": "dict",
        "datetime":"datetime"
    }

    functions = {
        'math': {
            'ln':          'log',
            'log':         'log',
            'tan':         'tan',
            'sin':         'sin',
            'cos':         'cos',
            'asin':        'asin',
            'acos':        'acos',
            'atan':         'atan',
            'sqrt':         'sqrt',
            'ceil':         'ceil',
            'round':        'round',
            'exp':         'exp',
            "floor": "floor",
            "isnan":"isnan"

        },
       'io': {
            'print':    translatePrint,
            'read':       'read',
            'read_file':  'File.ReadAllText',
            'write_file': 'File.WriteAllText'
        },
        'system': {
            'min': 'min',
            'max': 'max',
            'abs': 'abs',
            'pow': 'pow',
            'modulo': translateModulo,
            "copy":translateCopy,
            "integr":translateIntegr,
            'round':'round',
            'list':'list',
            'range':'range'
            
        },
        'datetime':{
            'datetime': 'datetime'
        }
    }
    constant = {
            
        'math':{
                
            'pi': 'pi'
                
                }            
    } 

    methods = {

        'int': {
            'float': 'float',
            'int':'int'
        },
        'float': {
            'int': 'int'
        },
        'str': {
            'int': 'int',
            'find': '.index'
        },
        'list': {
            'len': 'len',
            'append': '.append',
            'sum': 'sum',
            'pop': '.pop',
            'contains?': lambda node: Node("simpleCall", op='in', value=node.args, sequence=node.receiver, pseudo_type='Boolean'),
            'not contains?': translateNotContains,
            'index': '.index',
            'extend': '.extend',
            'allocate': lambda node: Node("assignment", target = node.receiver, value=Node("call", function = "array", args=[Node("str", value=b'f'),Node("binary_op", op="*", left = Node("list", elements=[Node("int", value="0")]),right=node.args)]))
        },
        'datetime':{
            'datetime':'datetime',
            'day':'day'
        },
        'array': {
            'len': 'len',
            'sum':"sum",
            'append': '.append',
            'allocate': lambda node: Node("assignment", target = node.receiver, value=Node("call", function = "array", args=[Node("str", value=b'f'),Node("binary_op", op="*", left = Node("list", elements=[Node("int", value="0")]),right=node.args)]))
        },
        'dict': {
			'len': 'len',
			'keys': translateDictkeys,
			'get' : '.get'

        }

    }
