# coding: utf8
from importlib.machinery import ExtensionFileLoader
from pycropml.transpiler.codeGenerator import CodeGenerator
from pycropml.transpiler.rules.javaRules import JavaRules
from pycropml.transpiler.generators.docGenerator import DocGenerator
from pycropml.transpiler.pseudo_tree import Node
import os
from pycropml.transpiler.interface import middleware
from path import Path
from pycropml.transpiler.Parser import parser
from pycropml.transpiler.ast_transform import AstTransformer, transform_to_syntax_tree
from pycropml.transpiler.antlr_py.api_declarations import Middleware
from pycropml.nameconvention import signature2
from pycropml.composition import ModelComposition
from copy import copy


class Custom_call(Middleware):

        
    def __init__(self, trees=None):
        self.trees = trees
        Middleware.__init__(self)
        self.extern = {}
              
    def process(self, tree):
        return self.transform(tree,in_block=False)
    
    def action_custom_call(self, tree):
        name = tree.function
        args = tree.args
        
        for m in self.trees.body:
            if m.type=="function_definition" and m.name==name:
                self.extern[name] = m   
        return self.transform_default(tree)

class JavaGenerator(CodeGenerator,JavaRules):
    """ This class contains the specific properties of
    Java language and use the NodeVisitor to generate a java
    code source from a well formed syntax tree.
    """
    
    def __init__(self, tree, model=None, name=None):
        CodeGenerator.__init__(self)
        JavaRules.__init__(self)
        self.tree = tree
        self.model=model
        self.name = name
        self.indent_with=' '*4
        self.initialValue=[] 
        self.index=False
        self.z = middleware(self.tree)
        self.z.transform(self.tree)
        self.therearedate=False
        self.ismodel=True
        if self.model: 
            self.doc= DocGenerator(model, '//')
            self.generator = JavaTrans([model])
            self.generator.model2Node()
            self.states = [st.name for st in self.model.states]  
            self.rates = [rt.name for rt in self.generator.rates ]
            self.auxiliary = [au.name for au in self.generator.auxiliary] 
            self.exogenous = [ex.name for ex in self.generator.exogenous]
            self.node_param = self.generator.node_param
            self.modparam=[param.name for param in self.node_param]
        self.funcname = ""

    def visit_notAnumber(self, node):
        self.write("Double.NaN")


    def visit_comparison(self, node):
        self.visit_binary_op(node)
        
    def visit_binary_op(self, node):
        op = node.op
        prec = self.binop_precedence.get(op, 0)
        self.operator_enter(prec)
        self.visit(node.left)
        self.write(u" %s " % self.binary_op[op].replace('_', ' '))
        if "type" in dir(node.right):
            if node.right.type=="binary_op" and  self.binop_precedence.get(str(node.right.op), 0) >= prec: # and node.right.op not in ("+","-") :
                self.write("(")
                self.visit(node.right)
                self.write(")")
            else:
                self.visit(node.right)
        else:
            self.visit(node.right)
        self.operator_exit()
    
    def visit_unary_op(self, node):
        op = node.operator
        prec = self.unop_precedence[op]
        self.operator_enter(prec)
        self.write(u"%s" % self.unary_op[op])
        self.visit(node.value)
        self.operator_exit()         
        
    def visit_breakstatnode(self, node):
        self.newline(node)
        self.write('break;')    

         
    def visit_import(self, node):
        pass

    def comment(self,doc):
        list_com = ["//" +x for x in doc.split('\n')]
        #com = '\n'.join(list_com)
        return list_com

    def visit_ExprStatNode(self, node):
        self.newline(node)
        if "value" in dir(node.expr) and node.expr.type=="str":
            com = self.comment(node.expr.value.decode('utf8'))
            for co in com: 
                if co!='//':
                    self.write(co)
                    self.newline()
        else:
            self.visit(node.expr)
            if not self.result[-1].endswith(";"): self.write(";") 
            
    


    def visit_cond_expr_node(self, node):
        self.visit(node.test)
        self.write(u" ? ")
        self.visit(node.true_val)     
        self.write(u" : ")
        self.visit(node.false_val) 
        
    def visit_if_statement(self, node):
        self.newline(node)
        self.write('if (')
        self.visit(node.test)
        self.write(')')
        self.newline(node)
        self.write('{')
        self.body(node.block)
        self.newline(node)
        self.write('}')
        while True:
            else_ = node.otherwise
            if len(else_) == 0:
                break
            elif len(else_) == 1 and else_[0].type=='elseif_statement':
                self.visit(else_[0])
            else:
                self.visit(else_)
                break
            break

    def visit_elseif_statement(self, node):
        self.newline()
        self.write('else if ( ')
        self.visit(node.test)
        self.write(')')
        self.newline(node)
        self.write('{')
        self.body(node.block)
        self.newline(node)
        self.write('}')        

    def visit_else_statement(self, node):
        self.newline()
        self.write('else')
        self.newline(node)
        self.write('{')        
        self.body(node.block)
        self.newline(node)
        self.write('}') 

    def visit_print(self):
        pass
    
    def visit_float(self, node):
        self.write(node.value)
        self.write("d")

    def visit_array(self, node):
        self.write("new %s "%(self.types2[node.pseudo_type[1]]))
        for j in node.elts:
            self.write("[")
            self.visit(j)
            self.write("]")
                
    def visit_dict(self, node):
        self.write("new ")
        self.visit_decl(node.pseudo_type)
        self.write(u'{')
        self.comma_separated_list(node.pairs)
        self.write(u'}')
    
    def visit_bool(self, node):
        self.write(node.value) #if node.value==True else self.write("false")
   
    def visit_standard_method_call(self, node):
        l = node.receiver.pseudo_type
        if isinstance(l, list):
            l = l[0]
        z = self.methods[l][node.message]        
        if callable(z):
            self.visit(z(node))
        else:
            if not node.args:
                self.write(z)
                self.write('(')
                self.visit(node.receiver)
                self.write(')')
            else:
                "%s.%s"%(self.visit(node.receiver),self.write(z))
                self.write("(")
                self.comma_separated_list(node.args)
                self.write(")")

            
    
    def visit_method_call(self, node):
        "%s.%s"%(self.visit(node.receiver),self.write(node.message))
        
                                
    def visit_index(self, node):
        self.visit(node.sequence)
        if node.sequence.pseudo_type[0]=="list" :
            self.write(".get(")
            self.visit(node.index) 
            self.write(")") 
        else:    
            self.write(u"[")
            if isinstance(node.index.type, tuple):
                self.emit_sequence(node.index)
            else:
                self.visit(node.index)
            self.write(u"]")

    def visit_sliceindex(self, node):
        self.visit(node.receiver)
        self.write(u"[")
        if node.message=="sliceindex_from":
            self.visit(node.args)
            self.write(u":")
        if node.message=="sliceindex_to":
            self.write(u":")
            self.visit(node.args)
        if node.message=="sliceindex":
            self.visit(node.args[0])
            self.write(u":")
            self.visit(node.args[1])
        self.write(u"]")
    
    def visit_assignment(self, node):
        if node.value.type == "binary_op" and node.value.left.type == "list":
            self.visit(node.target)
            self.write(".fill(")
            self.visit(node.value.right)
            self.write(", ")
            self.visit(node.value.left.elements[0])
            self.write(");")
        elif "function" in dir(node.value) and node.value.function.split('_')[0]=="model":
            name  = node.value.function.split('model_')[1]
            for m in self.model.model:
                if name == signature2(m):
                    name = signature2(m)
                    break
            self.write("_%s.Calculate_Model(s, s1, r, a, ex);"%(name))
            self.newline(node)
        else:
            self.newline(node)
            if "index" in dir(node.target) and node.target.sequence.pseudo_type[0]=="list": 
                self.write(node.target.sequence.name)
                self.write(".set(")
                self.visit(node.target.index)
                self.write(',')
                self.visit(node.value)
                self.write(");")
                self.newline(node)
            elif node.value.type == "standard_call" and node.value.function=="integr":
                self.write("%s = new ArrayList<>(%s);"%(node.target.name,node.value.args[0].name))
                self.newline(node)
                if isinstance(node.value.args[1].pseudo_type, list):
                    self.write("%s.addAll("%node.target.name)
                else: self.write("%s.add("%node.target.name)
                self.visit( node.value.args[1])
                self.write(");")

            elif node.target.type=="sliceindex" and node.target.message=="sliceindex" \
                and node.value.type=="sliceindex" and node.value.message=="sliceindex":
                    self.write(" System.arraycopy(")
                    self.visit(node.value.receiver)
                    self.write(", ")
                    self.visit(node.value.args[0])
                    self.write(", ")
                    self.visit(node.target.receiver)
                    self.write(", ")
                    self.visit(node.target.args[0])
                    self.write(", ")
                    if node.target.args[1].type=="binary_op" and node.target.args[1].op=="+":
                        self.visit(node.target.args[1].right)
                    else: self.visit(node.target.args[1])
                    self.write(");")

            elif node.target.type=="sliceindex" and node.target.message=="sliceindex" \
                and "name" in dir(node.value):
                    self.write("System.arraycopy(")
                    self.write(node.value.name)
                    self.write(", 0, ")
                    self.visit(node.target.receiver)
                    self.write(", ")
                    self.visit(node.target.args[0])
                    self.write(", ")
                    self.write(node.value.name)
                    self.write(".length);")
                    
            elif node.value.type == "standard_call" and node.value.function=="datetime":
                self.newline(node)
                if len(node.value.args)==3:node.value.args.extend([00,00,00])
                self.write(" %s = LocalDateTime.of(%s);"%(node.target.name,",".join(node.value.args)))
                self.newline(node)
            elif node.value.type =="standard_method_call" and node.value.message in ["keys", "values"]:
                self.write(node.target.name)
                self.write(".addAll(")
                self.visit(node.value)
                self.write(");")
                self.newline(node)     
            elif node.value.type=="array" and "elements" in dir(node.value):
                if "right" in dir(node.value.elements):
                    self.visit(node.target)
                    self.write("= new %s["%(self.types2[node.value.pseudo_type[1]]))
                    self.visit(node.value.elements.right)
                    self.write("];")
                    self.newline(node)
                else:
                    self.visit(node.target)
                    self.write(' = ')
                    self.write("new %s[] "%self.types2[node.value.pseudo_type[1]])

                if isinstance(node.value.elements, Node):
                    self.write("Arrays.fill(")
                    self.visit(node.target)
                    self.write(", ")
                    self.visit(node.value.elements.left.elements[0])  
                    self.write(");")  
                else:
                    self.visit(node.target)
                    self.write(' = ')
                    self.write("new %s[] "%self.types2[node.value.pseudo_type[1]])
                    self.write(u'{')
                    self.comma_separated_list(node.value.elements)
                    self.write(u'};') 
            elif node.value.type=="custom_call" and isinstance(node.value.pseudo_type, list) and node.value.pseudo_type[0]=="tuple":
                #self.write (f'{node.value.function} zz_{node.value.function} = Calculate_{node.value.function}(')
                self.write(f'zz_{node.value.function} = Calculate_{node.value.function}(')
                self.comma_separated_list(node.value.args)
                self.write(");")
                self.meta = Custom_call(self.module)
                r = self.meta.process(node)
                if node.value.function in self.meta.extern:
                    func = self.meta.extern[node.value.function]
                    outs = [n.name for n in func.block[-1].value.elements]
                    for k,out in enumerate(outs):
                        self.newline(node)
                        #print(node.value.function)
                        #print(node.target.y)
                        if "name" in dir (node.target.elements[k]): self.write(f'{node.target.elements[k].name} = zz_{node.value.function}.get{out}();')
                        else:
                            self.visit(node.target.elements[k])
                            self.write(f' = zz_{node.value.function}.get{out}();')
                        
            elif node.value.type=="none":
                pass
                
                              
            else:
                self.visit(node.target)
                self.write(' = ')
                self.visit(node.value) 
                self.write(";")
                self.newline(node)
    
    def visit_none(self, node):
        self.write("null")

    def visit_continuestatnode(self, node):
        self.newline(node)
        self.write('continue;')

    def transform_return(self, node):
        if self.funcname.startswith("model") or self.funcname.startswith("init"):
            returnvalues=node.block[-1].value
            if returnvalues.type=="tuple":
                output = [elt.name for elt in returnvalues.elements]
                node_output = [elt for elt in returnvalues.elements]
            else:
                output = [returnvalues.name]
                node_output = [returnvalues]
        else:
            if len(self.z.returns)==1:
                returnvalues=self.z.returns[0].value
                if returnvalues.type=="tuple":
                    output = [elt.name for elt in returnvalues.elements]
                    node_output = [elt for elt in returnvalues.elements]
                else:
                    if "name" in dir(returnvalues): 
                        output = [returnvalues.name]
                        node_output = [returnvalues]
                    else:                  
                        output = []
                        node_output = []  
            else: 
                output = []
                node_output = []
        return output, node_output

    def retrieve_params(self, node):
        parameters=[]
        node_params=[]
        for pa in node.params:
            parameters.append(pa.name)
            node_params.append(pa)
        return node.params

    def internal_declaration(self, node):
        statements = node.block
        if isinstance(statements, list):
            intern_decl = statements[0].decl if statements[0].type == "declaration" else None
            for stmt in statements[1:]:
                if stmt.type == "declaration":
                    intern_decl = (intern_decl if intern_decl else []) + stmt.decl
        else:
            intern_decl = statements.decl if statements.type == "declaration" else None
        return intern_decl
    
    def add_features(self, node):
        self.internal = self.internal_declaration(node)
        internal_name=[]
        if self.internal is not None:
            self.internal = self.internal if isinstance(self.internal,list) else [self.internal]
            for inter in self.internal:
                if 'elements' in dir(inter):
                    self.initialValue.append(Node(type="initial",name = inter.name, pseudo_type=inter.pseudo_type, value = inter.elements))
            internal_name= [e.name  for e in self.internal]
        self.params = self.retrieve_params(node)
        params_name = [e.name  for e in self.params]
        outputs = self.transform_return(node)[1]
        if not isinstance(outputs, list):
            outputs=[outputs]
        outputs_name = [e.name  for e in outputs]
        
        variables = self.params+self.internal if self.internal else self.params
        newNode=[]
        for var in variables:
            if var.pseudo_type in ["datetime", ["list","datetime"]]: self.therearedate=True 
            if var not in newNode:
                if var.name in params_name and var.name not in outputs_name:
                    var.feat = "IN"
                    newNode.append(var)
                if var.name in params_name and var.name in outputs_name:
                    var.feat = "INOUT"
                    newNode.append(var)
                if var.name in internal_name and var.name in outputs_name:
                    var.feat = "OUT"
                    newNode.append(var)
                if var.name in internal_name and var.name not in outputs_name:
                    newNode.append(var)
        return newNode    

    def visit_module(self, node):
        self.write(u"import  java.io.*;\nimport  java.util.*;\nimport java.text.ParseException;\nimport java.text.SimpleDateFormat;\nimport java.time.LocalDateTime;\n")
        self.extfuncs = []
        self.module=node
        if self.model is not None:
            self.write("public class %s"%signature2(self.model))
        else:
            self.write("public class Test")
        self.newline(node)
        self.write("{") 
        self.newline(node)
        self.indentation += 1
        self.visit(node.body)
        self.newline(node)
        self.indentation -= 1        
        self.newline(node)
        self.write("}") 
        
        self.newline(node)
        for ext in self.extfuncs:
            self.translate_final_class(ext)               
     
    def visit_function_definition(self, node):      
        self.newline(node)
        self.funcname = node.name
        self.meta = Custom_call(self.module)
        r = self.meta.process(node)
        if (not node.name.startswith("model_") and not node.name.startswith("init_")) :
            self.ismodel = False
            if node.name=="main":
                self.write("public static void main(String[] args)") 
            else:
                if node.return_type[0]=="tuple":
                    self.extfuncs.append(node)
                    self.extfunc = node
                    self.write(f"public {node.name} Calculate_{node.name} (")     
                else:
                    self.write("public static ")
                    self.visit_decl(node.return_type) if node.return_type else self.write("void")
                    self.write(" %s("%node.name)
                for i, pa in enumerate(node.params):
                    self.visit_decl(pa.pseudo_type)
                    self.write(" %s"%pa.name)
                    if i!= (len(node.params)-1):
                        self.write(', ')
                self.write(')')
            self.newline(node)
            self.write('{') 
            self.newline(node)
            self.meta = Custom_call(self.module)
            r = self.meta.process(node)
            if self.meta.extern:
                for j,k in self.meta.extern.items():
                    if k.return_type[0]=="tuple":
                        self.write(f"    {j} zz_{j};")
                        self.newline(node)
        else:
            self.meta = Custom_call(self.module)
            r = self.meta.process(node)
            if self.node_param and not node.name.startswith("init_") :
                for arg in self.node_param: 
                    self.newline(node) 
                    self.write ('private ') 
                    self.visit_decl(arg.pseudo_type)
                    self.write(" ")
                    self.write(arg.name) 
                    self.write(";") 
                    self.newline(node)                  
                    #self.generator.access([arg])
                    self.newline(node)#
                    self.write("public ")
                    self.gettype(arg)
                    self.write(' get%s()'%arg.name)
                    self.write(self.get_properties %(arg.name))
                    self.newline(extra=1)
                    self.write("public void set%s("%arg.name)
                    self.gettype(arg)
                    self.write(" _%s)"%arg.name)
                    self.write(self.set_properties%(arg.name, arg.name)) #
            self.write(self.constructor%signature2(self.model)) if not node.name.startswith("init_") else ""
            self.newline(node)      
            self.write("public void ")
            self.write(" Calculate_Model(") if not node.name.startswith("init_") else self.write("Init(")
            self.write('%sState s, %sState s1, %sRate r, %sAuxiliary a,  %sExogenous ex)'%(self.name, self.name,self.name, self.name, self.name))
            self.newline(node)
            self.write('{') 
            self.newline(node)
            if not node.name.startswith("init_"):
                self.write(self.doc.header)
                self.newline(node)
                self.write(self.doc.desc)
                self.newline(node)
                self.write(self.doc.inputs_doc)
                self.newline(node)
                self.write(self.doc.outputs_doc)
                self.newline(node)
            self.indentation += 1 
            if self.meta.extern:
                for j,k in self.meta.extern.items():
                    if k.return_type[0]=="tuple":
                        self.write(f"{j} zz_{j};")
                        self.newline(node)
            for arg in self.add_features(node) :
                if "feat" in dir(arg):
                    if arg.feat in ("IN","INOUT") :
                        self.newline(node)
                        if self.model and arg.name not in self.modparam:
                            self.visit_decl(arg.pseudo_type)
                            self.write(" ")
                            self.write(arg.name)
                            #print("iiiiiiii", arg.name)
                            if arg.name in self.states and not arg.name.endswith("_t1") :
                                self.write(" = s.get%s()"%arg.name)
                            elif arg.name.endswith("_t1") and arg.name in self.states:
                                self.write(" = s1.get%s()"%arg.name[:-3])
                            elif arg.name in self.rates:
                                self.write(" = r.get%s()"%arg.name)
                            elif arg.name in self.auxiliary:
                                self.write(" = a.get%s()"%arg.name) 
                            elif arg.name in self.exogenous:
                                self.write(" = ex.get%s()"%arg.name)                                     
                            else:
                                print("babababa", arg.name, arg.pseudo_type )
                                if arg.pseudo_type[0] =="list":
                                    self.write(" = new ArrayList<>(Arrays.asList())")
                                elif arg.pseudo_type[0] =="array":
                                    if not arg.elts:
                                        self.write(" = null;")
                                    else: 
                                        self.write(" = new %s[%s]"%(self.types[arg.pseudo_type[1]], arg.elts[0].value if "value" in dir(arg.elts[0]) else arg.elts[0].name))
                            self.write(";")                   
            self.indentation -= 1 
        self.newline(node)
        """if self.therearedate: 
            self.indentation += 1 
            self.write('SimpleDateFormat format = new SimpleDateFormat("yyyy-MM-dd");')
            self.indentation -= 1 """
        self.newline(node)
        self.body(node.block)
        self.newline(node)
        self.visit_return(node)
        self.newline(node)
        self.indentation -= 1 
        self.write('}') 
        self.newline(node)

        
    def translate_final_class(self, node):
        self.write(f"final class {node.name} ")
        self.write('{')
        self.newline(node)
        self.indentation +=1
        self.translate_getset(node.block[-1].value.elements)
        self.newline(node)
        self.translate_constructor(node)
        self.newline(node)
        self.indentation -=1
        self.write('}')
        
    def translate_constructor(self, node):
        self.write(f'public {node.name}(')
        for n in node.block[-1].value.elements:
            self.visit_decl(n.pseudo_type)
            self.write(" ")
            self.write(n.name)
            if n!= node.block[-1].value.elements[-1]:
                self.write(',')
        self.write(')')
        self.newline(node)
        self.write('{')
        self.indentation += 1
        self.newline(node)
        for n in node.block[-1].value.elements:
            self.write(f'this.{n.name} = {n.name};')
            self.newline(node)
        self.indentation -= 1 
        self.write('}')
    
    def translate_getset(self, node):
        for arg in node: 
            self.newline(node) 
            self.write ('private ') 
            self.visit_decl(arg.pseudo_type)
            self.write(" ")
            self.write(arg.name) 
            self.write(";") 
            self.newline(node)                  
            #self.generator.access([arg])
            self.newline(node)#
            self.write("public ")
            self.gettype(arg)
            self.write(' get%s()'%arg.name)
            self.write(self.get_properties %(arg.name))
            self.newline(extra=1)
            self.write("public void set%s("%arg.name)
            self.gettype(arg)
            self.write(" _%s)"%arg.name)
            self.write(self.set_properties%(arg.name, arg.name)) #
    
    
    def visit_constant(self, node):
        self.write(self.constant[node.library][node.name])
    def visit_custom_call(self, node):
        "TODO"
        self.visit_call(node)
        #self.write(".result")

    def visit_implicit_return(self, node):
        self.newline(node)
        if (not self.funcname.startswith("model_") and not self.funcname.startswith("init_")) :
            self.newline(node)
            if node.value is None:
                self.write('return')
            else:
                self.write('return ')
                if node.value.type == "tuple":
                    self.write(f"new {self.extfunc.name}(")
                    self.comma_separated_list(node.value.elements)
                    self.write(")")
                else: self.visit(node.value)
            self.write(";") 
    
    def visit_return(self, node):
        if self.model:
            self.newline(node)
            self.indentation += 1
            for arg in self.add_features(node):
                if "feat" in dir(arg):
                    if arg.feat in ("OUT", "INOUT"):
                        self.newline(node) 
                        if arg.name in self.states:
                            self.write("s.set%s(%s);"%(arg.name,arg.name))
                        if arg.name in self.rates:
                            self.write("r.set%s(%s);"%(arg.name,arg.name))
                        if arg.name in self.auxiliary:
                            self.write("a.set%s(%s);"%(arg.name,arg.name))
                        if arg.name in self.exogenous:
                            self.write("ex.set%s(%s);"%(arg.name,arg.name))
        else:
            self.newline(node)
            self.indentation += 1
    
    def visit_list(self, node):
        self.write(u'new ArrayList<>(Arrays.asList(')
        self.comma_separated_list(node.elements)
        self.write(u'))')
    
    def visit_tuple(self,node):
        self.write('new Pair[]')
        self.write("{")
        for n in node.elements:
            self.write('new Pair<>("%s", %s)'%(n.name, n.name)) if "name" in dir(n) else self.write('new Pair<>("%s", %s)'%(n.value, n.value))
            if n!= node.elements[len(node.elements)-1]: self.write(",")
        self.write("}")
    
    def visit_str(self, node):
        self.safe_double(node)
 
    def visit_declaration(self, node):
        self.newline(node)
        for n in node.decl:
            self.newline(node)
            if 'value' not in dir(n) and isinstance(n.pseudo_type, str) and n.pseudo_type!="datetime":
                self.write(self.types[n.pseudo_type])
                self.write(' %s;'%n.name) 
            if 'elements' not in dir(n) and n.type in ("list","array"):
                if n.type=="list":
                    self.write("List<%s> %s = new ArrayList<>(Arrays.asList());"%(self.types2[n.pseudo_type[1]],n.name))
                if n.type=="array":
                    self.write(f"{self.types2[n.pseudo_type[1]]}[]")
                    self.write(f" {n.name} = null ;") if "dim" not in dir(n) or n.dim ==0 else self.write(f" {n.name} = ")
                    if "elts" in dir(n) and n.elts:
                        self.write(f" new {self.types2[n.pseudo_type[1]]} ")
                        for j in n.elts:
                            self.write("[")
                            self.visit(j)
                            self.write("]")
                        self.write(";")
            if 'value' in dir(n) and n.type in ("int", "float", "str", "bool"):
                self.write("%s %s"%(self.types[n.type], n.name))
                self.write(" = ")
                if n.type=="local":
                    self.write(n.value)
                else: self.visit(n.value) if isinstance(n.value, Node) else self.write(n.value)
                self.write(";") 
            elif 'elements' in dir(n) and n.type in ("list", "tuple", "array"):
                if n.type=="list":
                    self.visit_decl(n.pseudo_type)
                    self.write(n.name)
                    self.write(" = new ArrayList <>(Arrays.asList") 
                    #self.visit_decl(n.pseudo_type)
                    self.write(u'(')
                    self.comma_separated_list(n.elements)
                    self.write(u'));')  
                
                if n.type=="array":
                    self.visit_decl(n.pseudo_type)
                    self.write(n.name)
                    self.write(" = ")  
                    self.write(u'{')
                    self.comma_separated_list(n.elements)
                    self.write(u'};') 
                    
         
            elif  n.type=='datetime':
                self.newline(node)
                self.write("LocalDateTime; ")
                #self.write(n.name) 
                #self.write("= new Date();") """   
            elif 'pairs' in dir(n) and n.type=="dict":
                self.visit_decl(n.pseudo_type)
                self.write(n.name)
                self.write(" = new ") 
                self.visit_decl(n.pseudo_type)
                self.write("()")               
                self.write(u'{{')
                self.comma_separated_list(n.pairs)
                self.write(u'}};')
                
        self.newline(node)
    
    def visit_list_decl(self, node):        
        if not isinstance(node[1], list):
            self.write(self.types2[node[1]])
            self.write('>')
        else:
            node = node[1]
            self.visit_decl(node)
            self.write('>')
    
    def visit_dict_decl(self, node):  
        self.write(self.types2[node[1]])
        self.write(",")        
        if not isinstance(node[2], list):
            self.write(self.types2[node[2]])
            self.write('>')
        else:
            node = node[2]
            self.visit_decl(node)
            self.write('>')
    
    def visit_tuple_decl(self, node):
        self.visit_decl(node[0])
        for n in node[1:-1]:
            if n in ["int","float", "str"]: self.write(self.types2[n])
            else: self.visit_decl(n)
            self.write(",")
        if node[-1] in ["int","float", "str"]: self.write(self.types2[n])
        else: self.visit_decl(node[-1])
        self.write('> ')
    
    def visit_float_decl(self, node):
        self.write(self.types[node])

    def visit_datetime_decl(self, node): 
        self.write(self.types2[node])

    def visit_int_decl(self, node):
        self.write(self.types[node])

    def visit_str_decl(self, node):
        self.write(self.types[node])
        
    def visit_bool_decl(self, node):
        self.write(self.types[node])        

    def visit_array_decl(self, node):
        #self.visit_decl(node[1])
        self.write(self.types2[node[1]])
        self.write(" []")
        
    def visit_decl(self, node):
        if isinstance(node, list):
            if node[0]=="list":
                self.write('List<')
                self.visit_list_decl(node)
            if node[0] == "dict":
                self.write("HashMap<")
                self.visit_dict_decl(node)
            if node[0]=="tuple":
                self.write("Pair[]")
            if node[0]=="array":
                self.visit_array_decl(node)
        else:
            if node=="float":
                self.visit_float_decl(node)
            if node =="int":
                self.visit_int_decl(node)
            if node =="str":
                self.visit_str_decl(node)
            if node =="bool":
                self.visit_bool_decl(node)                
            if node =="datetime":
                self.visit_datetime_decl(node) 
            
    def visit_pair(self, node):
        self.write(u'put(')
        self.visit(node.key)
        self.write(u", ")
        self.visit(node.value)
        self.write(u');')
            
    def visit_call(self, node):
        want_comma = []
        def write_comma():
            if want_comma:
                self.write(', ')
            else:
                want_comma.append(True)
        if "attrib" in dir(node) and node.namespace!="math":
             self.write(u"%s.%s"%(node.namespace,self.visit(node.function)))
        else:
            if callable(node.function):
                self.visit(node.function(node))
            else: 
                self.write(node.function)
                self.write('(')
                for arg in node.args:
                    write_comma()
                    self.visit(arg)
                self.write(')')
    
    def visit_standard_call(self, node):       
        node.function = self.functions[node.namespace][node.function]
        self.visit_call(node)  
        
    def visit_importfrom(self, node):
        pass
    
    def visit_for_statement(self, node):
        self.newline(node)
        self.write("for(")
        if "iterators" in dir(node):
            self.visit(node.iterators) 
        if "sequences" in dir(node):
            self.visit(node.sequences)
            self.write(')')
            self.newline(node)
        self.newline(node)
        self.write('{')
        if "iterators" in dir(node):
            self.newline(node)
            self.indentation += 1 
            self.write("%s = %s_cyml;"%(node.iterators.iterator.name, node.iterators.iterator.name))
            self.indentation -= 1
        self.body(node.block)
        self.newline(node)
        self.write('}')  
          
    def visit_for_iterator_with_index(self, node):
        self.visit(node.index)
        self.write(' , ')
        self.visit(node.iterator)


    def visit_for_sequence_with_index(self, node):     
        pass

    def visit_for_iterator(self, node):
        self.write("%s "%self.types2[node.iterator.pseudo_type].capitalize())
        self.visit(node.iterator)
        self.write("_cyml")
        self.write(" : ")
           
    
    def visit_for_range_statement(self, node):
        self.newline(node)
        self.write("for (")
        self.visit(node.index)
        self.write("=")
        self.visit(node.start)
        self.write(' ; ')
        self.visit(node.index)
        self.write("!=")        
        self.visit(node.end)
        self.write(' ; ')
        self.visit(node.index)
        self.write("+=")
        if "value" in dir(node.step) and node.step.value==1: 
            self.write("1")
        else:      
            self.visit(node.step)
        self.write(')')
        self.newline(node)
        self.write('{')        
        self.body(node.block)
        self.newline(node)
        self.write('}')        
        
    def visit_while_statement(self, node):
        self.newline(node)
        self.write('while ( ')
        self.visit(node.test)
        self.write(')')
        self.newline(node)
        self.write('{')
        self.body_or_else(node)
        self.newline(node)
        self.write('}')        

    def gettype(self, arg):
        if isinstance(arg.pseudo_type, list):
            if arg.pseudo_type[0] in ("list", "array"):
                self.visit_decl(arg.pseudo_type)
                #self.write(' ' + arg.name)                                                            
        else:
            self.visit_decl(arg.pseudo_type)

from copy import deepcopy

class JavaTrans(CodeGenerator,JavaRules):
    """ This class used to generates states, rates, auxiliary and exogenous classes
    for java language.
    """
    
    def __init__(self, models):
        CodeGenerator.__init__(self)
        JavaRules.__init__(self)
        self.models=models
        self.states=[]
        self.rates=[]
        self.auxiliary=[]
        self.exogenous=[]
        self.extern =[] 
        self.modparam=[] 
    DATATYPE={
        "INT": "int",
        "DOUBLE": "float",
        "STRING":"str",
        "DATEARRAY":["array","datetime"],
        "INTARRAY":["array","int"],
        "DOUBLEARRAY":["array","float"],
        "STRINGARRAY":["array","str"],
        "STRINGLIST":["list","str"],
        "DOUBLELIST":["list","float"],
        "INTLIST":["list","int"],
        "DATELIST":["list","datetime"],
        "BOOLEAN":'bool',
        "DATE":"datetime"
    }
   
    def model2Node(self):
        variables=[]
        varnames=[]
        for m in self.models:
            if "function" in dir(m):
                for f in m.function:
                    self.extern.append(f.name)
            for inp in m.inputs:
                if inp.name not in varnames:
                    category = inp.variablecategory if "variablecategory" in dir(inp) else inp.parametercategory
                    variables.append(inp)
                    varnames.append(category + inp.name)
                    if isinstance(m, ModelComposition):
                        k_ = get_key(m.diff_in, inp.name )
                        if k_:
                            node_ = deepcopy(inp)
                            node_.name = k_
                            variables.append(node_)
                            varnames.append(category+k_)
            for out in m.outputs:
                if out.name not in varnames:
                    category = out.variablecategory if "variablecategory" in dir(out) else out.parametercategory
                    variables.append(out)
                    varnames.append(category + out.name)
                    if isinstance(m, ModelComposition):
                        k_ = get_key(m.diff_out, out.name )
                        if k_:
                            node_ = deepcopy(out)
                            node_.name = k_
                            variables.append(node_)
                            varnames.append(category + k_)
            if "ext" in dir(m):
                for ex in m.ext:
                    if ex.name not in varnames:
                        category = ex.variablecategory if "variablecategory" in dir(ex) else ex.parametercategory
                        variables.append(ex)
                        varnames.append(category + ex.name) 
        #print(len(variables))
        st = []
        for var in variables:
            if "variablecategory" in dir(var):
                if var.variablecategory=="state" and not var.name.endswith("_t1") and var.name not in st:
                    self.states.append(var)
                    st.append(var.name)
                if var.variablecategory=="state" and var.name.endswith("_t1"):
                    if var.name[:-3] in st:
                        for i, j in enumerate(self.states):
                            if var.name[:-3] in j.name:
                                self.states.remove(j)
                                break
                    z = copy(var)
                    z.name = z.name[:-3]
                    self.states.append(z)
                    st.append(z.name)
                                                 
                if var.variablecategory=="rate" :
                    self.rates.append(var)
                if var.variablecategory=="auxiliary":
                    self.auxiliary.append(var)
                if var.variablecategory=="exogenous":
                    self.exogenous.append(var)
            if "parametercategory" in dir(var):
                self.modparam.append(var)

        def create(typevar):
            node_typevar=[]
            for st in typevar:
                if st.datatype in ("INT","DOUBLE","BOOLEAN","STRING","INTLIST","DOUBLELIST","STRINGLIST", "DATE", "DATELIST"):
                    node=Node(type="local", name=st.name, pseudo_type=self.DATATYPE[st.datatype])
                    node_typevar.append(node)
                if st.datatype in ("INTARRAY","DOUBLEARRAY","STRINGARRAY", "DATEARRAY", ):
                    if st.len.isdigit():
                        elts = Node(type='int', value= st.len, pseudo_type= 'int')
                    else:
                        elts = Node(type='name', name= st.len, pseudo_type= 'int')
                    node=Node(type="local", name=st.name, elts=[elts], pseudo_type=self.DATATYPE[st.datatype])
                    node_typevar.append(node)
            return node_typevar
        self.node_states = create(self.states)
        self.node_rates= create(self.rates)
        self.node_auxiliary= create(self.auxiliary) 
        self.node_exogenous= create(self.exogenous)
        self.node_param=create(self.modparam)   

        
    def private(self,node):
        vars = []
        for arg in node:
            if arg.name not in vars:
                self.newline(node) 
                self.write ('private ') 
                self.visit_decl(arg.pseudo_type)
                self.write(" ")
                self.write(arg.name) 
                self.write(";")
                vars.append(arg.name)


    def getset(self,node):
        vars = []
        for arg in node:  
            if arg.name not in vars:     
                self.newline(node)
                self.write("public ")
                self.gettype(arg)
                self.write(' get%s()'%arg.name)
                self.write(self.get_properties %(arg.name))
                self.newline(extra=1)
                self.write("public void set%s("%arg.name)
                self.gettype(arg)
                self.write(" _%s)"%arg.name)
                self.write(self.set_properties%(arg.name, arg.name)) 
                vars.append(arg.name)

    def access(self, node):
        self.private(node)
        self.getset(node)

    def gettype(self, arg):
        if isinstance(arg.pseudo_type, list):
            if arg.pseudo_type[0] in ("list", "array"):
                self.visit_decl(arg.pseudo_type)                                                          
        else:
            self.visit_decl(arg.pseudo_type)

    def copyconstructor(self,node):
        tab=' '*4
        for arg in node:
            self.newline(node)
            if isinstance(arg.pseudo_type, list):
                if arg.pseudo_type[0] =="list":
                    self.write("%sList <%s> _%s = new ArrayList<>();"%(tab*2,self.types2[arg.pseudo_type[1]],arg.name))
                    self.write(self.copy_constrList%(self.types2[arg.pseudo_type[1]],arg.name,arg.name, arg.name, arg.name))
                if arg.pseudo_type[0] =="array":
                    self.write("%s%s = new %s[%s];"%(tab*2,arg.name, self.types2[arg.pseudo_type[1]], arg.elts[0].value if "value" in dir(arg.elts[0]) else f'toCopy.get{arg.name}().length'))
                    self.write(self.copy_constrArray%(arg.elts[0].value if "value" in dir(arg.elts[0]) else f'toCopy.get{arg.name}().length',arg.name,arg.name))
            else:
                self.write("%sthis.%s = toCopy.get%s();"%(tab*2,arg.name, arg.name))


    def visit_list_decl(self, node):
        if not isinstance(node[1], list):
            self.write(self.types2[node[1]])
            self.write('>')
        else:
            node = node[1]
            self.visit_decl(node)
            self.write('>')

    def visit_dict_decl(self, node):
        self.write(self.types2[node[1]])
        self.write(",")
        if not isinstance(node[2], list):
            self.write(self.types2[node[2]])
            self.write('>')
        else:
            node = node[2]
            self.visit_decl(node)
            self.write('>')

    def visit_tuple_decl(self, node):
        self.visit_decl(node[0])
        for n in node[1:-1]:
            self.visit_decl(n)
            self.write(",")
        self.visit_decl(node[-1])
        self.write('> ')

    def visit_float_decl(self, node):
        self.write(self.types[node])

    def visit_int_decl(self, node):
        self.write(self.types[node])

    def visit_str_decl(self, node):
        self.write(self.types[node])

    def visit_bool_decl(self, node):
        self.write(self.types[node])

    def visit_array_decl(self, node):
        self.write(self.types2[node[1]])
        self.write(" []")

    def visit_datetime_decl(self, node):
        self.write(self.types2[node])

    def visit_decl(self, node):
        if isinstance(node, list):
            if node[0] == "list":
                self.write('List<')
                self.visit_list_decl(node)
            if node[0] == "dict":
                self.write("TreeMap<")
                self.visit_dict_decl(node)
            if node[0] == "tuple":
                self.write('Tuple<')
                self.visit_tuple_decl(node)
            if node[0] == "array":
                self.visit_array_decl(node)
        else:
            if node == "float":
                self.visit_float_decl(node)
            if node == "int":
                self.visit_int_decl(node)
            if node == "str":
                self.visit_str_decl(node)
            if node == "bool":
                self.visit_bool_decl(node)
            if node == "datetime":
                self.visit_datetime_decl(node) 


    def generate(self, nodes, typ): 
        self.write("public class %s"%typ)
        self.newline()
        self.write("{")
        self.indentation += 1        
        self.newline()
        self.private(nodes)
        self.newline()
        self.write(self.constructor%(typ))     ########### constructor
        self.newline()
        self.write(self.copy_constr%(typ,typ))###### copy constructor 
        self.copyconstructor(nodes)
        self.newline()
        self.write('    }')
        self.newline()
        self.write('}')     
        self.getset(nodes)
        self.indentation -= 1
        self.newline()
        self.write('}')
        self.newline()


def to_struct_java(models, rep, name):
    generator = JavaTrans(models)
    generator.result=[u"import  java.io.*;\nimport  java.util.*;\nimport java.time.LocalDateTime;\n"]
    generator.model2Node()
    states = generator.node_states
    generator.generate(states, "%sState"%name)
    z= ''.join(generator.result)
    filename = Path(os.path.join(rep,"%sState.java"%name))
    with open(filename, "wb") as tg_file:
        tg_file.write(z.encode('utf-8'))
    rates = generator.node_rates
    generator.result=[u"import  java.io.*;\nimport  java.util.*;\nimport java.time.LocalDateTime;\n"]
    generator.generate(rates, "%sRate"%name)
    z1= ''.join(generator.result)
    filename = Path(os.path.join(rep, "%sRate.java"%name))
    with open(filename, "wb") as tg1_file:
        tg1_file.write(z1.encode('utf-8'))
    auxiliary = generator.node_auxiliary
    generator.result=[u"import  java.io.*;\nimport  java.util.*;\nimport java.time.LocalDateTime;\n"]
    generator.generate(auxiliary, "%sAuxiliary"%name)
    z2= ''.join(generator.result)
    filename = Path(os.path.join(rep/"%sAuxiliary.java"%name))
    with open(filename, "wb") as tg2_file:
        tg2_file.write(z2.encode('utf-8')) 

    exogenous = generator.node_exogenous
    generator.result=[u"import  java.io.*;\nimport  java.util.*;\nimport java.time.LocalDateTime;\n"]
    generator.generate(exogenous, "%sExogenous"%name)
    z2= ''.join(generator.result)
    filename = Path(os.path.join(rep/"%sExogenous.java"%name))
    with open(filename, "wb") as tg2_file:
        tg2_file.write(z2.encode('utf-8'))  
    return 0



''' Java composite'''


class JavaCompo(JavaTrans, JavaGenerator):
    """ This class used to generates states, rates, auxiliary and exogenous classes
        for java language.
    """
    def __init__(self, tree, model=None, name=None):
        self.tree = tree
        self.model=model
        self.name = name
        self.init=False
        JavaGenerator.__init__(self,tree, model, self.name)
        JavaTrans.__init__(self,[model])
        self.modelparams = [pa.name for pa in self.model.inputs if "parametercategory" in dir(pa)]
        self.model2Node()
        self.statesName = [st.name for st in self.states]
        self.ratesName = [rt.name for rt in self.rates]
        self.auxiliaryName = [au.name for au in self.auxiliary]
        self.exogenousName = [au.name for au in self.exogenous]
       # self.model2Node()

    def visit_module(self, node):
        self.write("public class %sComponent"%signature2(self.model))
        self.init = False
        self.newline(node)
        self.write("{") 
        self.newline(node)
        self.indentation += 1     
        self.visit(node.body)
        self.newline(node)
        if "function" in dir(self.model) and self.model.function:
            func_name = os.path.split(self.model.function[0].filename)[1]
            func_path = os.path.join(self.model.path,"src","pyx", func_name)
            func_tree=parser(Path(func_path))  
            newtree = AstTransformer(func_tree, func_path)
            dictAst = newtree.transformer()
            nodeAst= transform_to_syntax_tree(dictAst)
            self.model=None
            self.visit(nodeAst.body)
        self.indentation -= 1        
        self.newline(node)
        self.write("}")         

    def visit_function_definition(self, node):      
        self.newline(node)
        self.add_features(node)
        self.write(self.constructor%("%sComponent"%signature2(self.model))) if not node.name.startswith("init_") else self.write("")
        self.newline(extra=1)          
        self.write(self.instanceModels())  if not node.name.startswith("init_") else self.write("")     
        self.newline(extra=1)
        if self.node_param and not node.name.startswith("init_"):
            vars = []
            for arg in self.node_param:  
                if arg.name in self.getRealInputs() and arg.name not in vars:                        
                    self.newline(extra=1)
                    self.write("public ")
                    self.gettype(arg)
                    self.write(' get%s()'%arg.name)
                    x = self.get_mo(arg.name)
                    self.write(self.get_properties_compo%(list(x[0].keys())[0], list(x[0].values())[0]))               
                    #b="\n        ".join(self.setCompo(arg.name))
                    self.newline(node)
                    self.write("public void set%s("%arg.name)
                    self.gettype(arg)
                    self.write(" _%s){"%arg.name) 
                    self.newline(1)
                    self.setCompo(arg.name) 
                    self.newline(1) 
                    self.write("}") 
                    vars.append(arg.name)                
                    #self.write(self.set_properties_compo%(b))
        self.newline(node)      
        self.write("public void ")
        if not node.name.startswith("init_"):
            self.write(" Calculate_Model(")
        else:
            self.write("Init(")
            self.init=True
        self.write('%sState s, %sState s1, %sRate r, %sAuxiliary a, %sExogenous ex)'%(self.name,self.name,self.name,self.name,self.name))
        self.newline(node)
        self.write('{') 
        self.newline(node)
        self.body(node.block)
        self.newline(node)
        self.visit_return(node)
        self.newline(node)
        #self.indentation -= 1 
        self.write('}') 
        self.newline(node)
        if not node.name.startswith("init_"):
            self.private(self.node_param)
            typ = self.model.name+"Component"
            self.write(self.copy_constr_compo%(typ,typ))###### copy constructor 
            self.copyconstructor(self.node_param)
            self.newline(extra=1)
            self.write('}') 
        else: 
            self.init = True
            for arg in self.add_features(node):
                if "feat" in dir(arg):
                    if arg.feat in ("OUT", "INOUT"):
                        self.newline(node) 
                        if arg.name in self.states:
                            self.write("s.set%s(%s);"%(arg.name,arg.name))
                        if arg.name in self.rates:
                            self.write("r.set%s(%s);"%(arg.name,arg.name))
                        if arg.name in self.auxiliary:
                            self.write("a.set%s(%s);"%(arg.name,arg.name))
                        if arg.name in self.exogenous:
                            self.write("ex.set%s(%s);"%(arg.name,arg.name))
            self.write("")
        self.newline(node)

    def getRealInputs(self):
        inputs=[]
        for inp in self.models[0].inputlink:
            var = inp["source"]
            inputs.append(var)
        return inputs
    
    def visit_declaration(self, node):
        if self.init is True:
            return JavaGenerator(self.tree).visit_declaration(node)
        else: 
            pass
            
    
    def visit_return(self, node):
        self.newline(node)
    
    def visit_implicit_return(self, node):
        pass

    """def visit_local(self, node):
        if node.name in self.statesName:
            self.write("s.set%s"%node.name)
        elif node.name in self.ratesName:
            self.write("r.set%s"%node.name)
        elif node.name in self.auxiliaryName:
            self.write("a.set%s"%node.name)
        elif node.name in self.exogenousName:
            self.write("ex.set%s"%node.name)
        else: self.write(node.name)"""

    def visit_assignment(self, node):
       
        if "function" in dir(node.value) and node.value.function.split('_')[0]=="model":
            name  = node.value.function.split('model_')[1]
            for m in self.model.model:
                if name.lower() == signature2(m).lower():
                    name = signature2(m)
                    break
            self.write("_%s.Calculate_Model(s, s1, r, a, ex);"%(name))
            self.newline(node)

        elif "function" in dir(node.value) and node.value.function.split('_')[0]=="init":
            name  = node.value.function.split('init_')[1]
            for m in self.model.model:
                if name.lower() == signature2(m).lower():
                    name = signature2(m)
                    break
            self.write("_%s.Init(s, s1, r, a, ex);"%(name))
            self.newline(node)
            
        else: 
            print(node.value.y)   
            if node.value.name not in self.modelparams:
                if node.target.name in self.statesName:
                    self.write("s.set")
                elif node.target.name in self.ratesName:
                    self.write("r.set")
                elif node.target.name in self.auxiliaryName:
                    self.write("a.set")
                elif node.target.name in self.exogenousName:
                    self.write("ex.set")
                self.visit(node.target)
                self.write('(')
                if node.value.name in self.statesName:
                    self.write("s.get")
                elif node.value.name in self.ratesName:
                    self.write("r.get")
                elif node.value.name in self.auxiliaryName:
                    self.write("a.get")
                elif node.value.name in self.exogenousName:
                    self.write("ex.get")
                self.visit(node.value) 
                self.write("());")
            else:
                #x = self.getmo(node.target.name)
                pass
            self.newline(node)


    def setCompo(self, p):
        a=[]
        mo = self.get_mo(p)
        for mi in mo:
            self.write("_%s.set%s(_%s);"%(list(mi.keys())[0],list(mi.values())[0], p))            
            self.newline(1) 
        return a

 
    def get_mo(self,varname):
        listmo=[]
        for inp in self.model.inputlink:
            var = inp["source"]
            mod = inp["target"].split(".")[0]
            modvar = inp["target"].split(".")[1]
            if var==varname:
                listmo.append({mod:modvar})
        return listmo
    
    def instanceModels(self):
        inst=[]
        for m in self.model.model:
            name = signature2(m)
            inst.append("%s _%s = new %s();"%(name, name, name))
        modinst = '\n    '.join(inst)
        return modinst
      
    def copyconstructor(self,node):
        for arg in node:
            self.newline(node)
            if arg.name in self.getRealInputs():
                if isinstance(arg.pseudo_type, list):
                    if arg.pseudo_type[0] =="list":
                        self.write("    this.%s"%self.copy_constrList%(arg.name,arg.name,arg.name))
                    if arg.pseudo_type[0] =="array":
                        self.write("    %s"%self.copy_constrArray%(arg.elts[0].value if "value" in dir(arg.elts[0]) else f'toCopy.get{arg.name}().length',arg.name,arg.name))
                else:
                    self.write("    this.%s = toCopy.get%s();"%(arg.name, arg.name)) 

    def initCompo(self):
        pass

 
def argsToStr(args):
    t=[]
    for arg in args:
        t.append(arg.value)
    return '"%s"'%('-'.join(t))

def get_key(my_dict, val):
    for key, value in my_dict.items():
        if val == value:
            return key
    return None