
from nine.lexer import lex
from nine.parser import parse
from nine.codegenerator import CodeGenerator
from nine import semantic

class Driver(object):
    def __init__(self):
        self.references = []

    def addReference(self, assemblyName):
        self.references.append(assemblyName)

    def _loadAssembly(self, assemblyName):
        from CLR.System import String
        from CLR.System.Reflection import Assembly
        from CLR.System.IO import FileLoadException

        try:
            # HACK around WEIRD bug in Python .NET
            clrName = String(assemblyName)

            assembly = Assembly.Load(clrName)
            if assembly is not None:
                return assembly

        except FileLoadException:
            print assemblyName
            raise

    def _scanAssembly(self, globalNs, assemblyName):
        from ast.namespace import Namespace
        from ast.vartypes import Type
        from ast.external import ExternalType

        from CLR import System
        from CLR.System import Reflection
        from CLR.System.Reflection import Assembly

        #assembly = Assembly.LoadWithPartialName(assemblyName)
        assembly = self._loadAssembly(assemblyName)
        if assembly is None:
            raise Exception, 'Unable to load assembly %s' % assemblyName

        namespaces = globalNs

        def getNs(name, curNs=None):
            ns = curNs or globalNs

            if len(name) == 0:
                return curNs
            else:
                n = name[0]

                if n not in ns.symbols:
                    ns.symbols[n] = Namespace(n)

                return getNs(name[1:], ns.symbols[n])

        '''Absurdly complex, given how little it does. :P

        For each type whose full name does not begin with something freaky like $
        create namespace instances and a Type instance within the whole heirarchy
        to correspond with all the types in the assembly.

        For instance, storing the System.Console class requires creating or reopening
        of the System namespace, in which the Console Type gets poured.

        FIXME: nested types are not correctly handled at all.
        '''
        for type in assembly.GetTypes():
            if not type.Name[0].isalpha() and type.Name[0] != '_':
                continue

            if type.IsNestedPublic:
                outerName = type.FullName
                outerName, innerName = type.FullName.split('+', 1)

                outerName = outerName.split('.')
                outerNs = getNs(outerName[:-1])
                assert outerName[-1] in outerNs.symbols, "Internal badness: have to process a nested class before we've processed the enclosing class."

                outerClass = outerNs.symbols[outerName[-1]]
                outerClass.symbols[type.Name] = ExternalType.getNineType(type)

            else:
                if type.Namespace is None:
                    ns = globalNs
                else:
                    ns = getNs(type.Namespace.split('.'))

                ns.symbols[type.Name] = ExternalType.getNineType(type)

        return namespaces

    def fixPrimitives(self):
        # HACK: make the primitive types match up. (disregard this, as it is wholly insane)
        import CLR
        from nine.util import typeToType as t2t
        from ast.external import ExternalType
        from ast import vartypes

        vartypes.IntType = ExternalType.getNineType(t2t(CLR.System.Int32))
        vartypes.FloatType = ExternalType.getNineType(t2t(CLR.System.Single))
        vartypes.CharType = ExternalType.getNineType(t2t(CLR.System.Char))
        vartypes.StringType = ExternalType.getNineType(t2t(CLR.System.String))
        vartypes.BooleanType = ExternalType.getNineType(t2t(CLR.System.Boolean))
        vartypes.VoidType = ExternalType.getNineType(t2t(CLR.System.Void))

        vartypes.PrimitiveTypes = {
            'int' : vartypes.IntType,
            'float' : vartypes.FloatType,
            'boolean' : vartypes.BooleanType,
            'char' : vartypes.CharType,
            'string' : vartypes.StringType,
            'void' : vartypes.VoidType
        }

    def parseFile(self, fileName):
        source = file(fileName, 'rt').read()
        return self.parseString(source, fileName)

    def parseString(self, source, fileName=None):
        tokens = lex(source, fileName)
        return parse(tokens)

    def scanAssemblies(self, assemblies):
        from ast.namespace import Namespace

        globalNs = Namespace('')
        for ref in self.references:
            globalNs = self._scanAssembly(globalNs, ref)

        return globalNs

    def compileProgram(self, ast, outputName):
        globalNs = self.scanAssemblies(self.references)

        self.fixPrimitives()

        # Fill globalNs with declared symbols
        for decl in ast:
            if hasattr(decl, 'name'):
                globalNs.symbols[decl.name] = decl

        globalScope = semantic.makeGlobalScope(globalNs.symbols)
        st = semantic.semantic(ast, globalScope)

        gen = CodeGenerator()
        gen.createProgram(outputName, st)

    def compileString(self, source, outputName):
        ast = self.parseString(source)

        self.compileProgram(ast, outputName)

    def compile(self, sources, outputName):
        ast = list()

        for source in sources:
            ast.extend(self.parseFile(source))

        self.compileProgram(ast, outputName)
