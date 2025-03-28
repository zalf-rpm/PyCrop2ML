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

class CymlRules(GeneralRule):

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
                 "&":"&",
                 "is":"is",
                "is not":"is not"
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
            "pow": "pow",
            "isnan": "isnan"

        },
       'io': {
            'print':    translatePrint,
            'read':       'read',            # not correct TODO
            'read_file':  'File.ReadAllText', # not correct TODO
            'write_file': 'File.WriteAllText' # not correct TODO
        },
        'system': {
            'min': 'min',
            'max': 'max',
            'abs': 'abs',
            'pow': 'pow',
            'modulo': translateModulo,
            "copy":translateCopy,
            "integr":translateIntegr,
            "round":"round"
            
            
        },
        'datetime':{
            'datetime': 'datetime',
            
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
            'int':'int',
            'double':'float'
        },
        'float': {
            'int': 'int'
        },
        'str': {
            'int': 'int',
            'find': '.index',
            'index':'.index'
        },
        'list': {
            'len': 'len',
            'append': '.append',
            'allocate':".allocate",
            'sum': 'sum',
            'pop': '.pop',
            'contains?': lambda node: Node("simpleCall", op='in', value=node.args, sequence=node.receiver, pseudo_type='Boolean'),
            'not contains?': translateNotContains,
            'index': '.index',
            'extend': '.extend'
        },
        'datetime':{
            'datetime':'datetime',
            'day':'day'
        },
        'array': {
            'len': 'len',
            'append': '.append',
            'allocate':".allocate",
            'sum': 'sum',
        },
        'dict': {
			'len': 'len',
			'keys': translateDictkeys,
			'get' : '.get'

        }

    }
