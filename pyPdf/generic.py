# vim: sw=4:expandtab:foldmethod=marker
#
# Copyright (c) 2006, Mathieu Fenniak
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# * Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
# * The name of the author may not be used to endorse or promote products
# derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.


"""
Implementation of generic PDF objects (dictionary, number, string, and so on)
"""
__author__ = "Mathieu Fenniak"
__author_email__ = "mfenniak@pobox.com"

import re
from utils import readNonWhitespace

class BooleanObject(object):
    def __init__(self, value):
        self.value = value

    def writeToStream(self, stream):
        if self.value:
            stream.write("true")
        else:
            stream.write("false")

    def readFromStream(stream):
        word = stream.read(4)
        if word == "true":
            return BooleanObject(True)
        elif word == "fals":
            stream.read(1)
            return BooleanObject(False)
        assert False
    readFromStream = staticmethod(readFromStream)


class ArrayObject(list):
    def writeToStream(self, stream):
        stream.write("[")
        for data in self:
            stream.write(" ")
            data.writeToStream(stream)
        stream.write(" ]")

    def readFromStream(stream, pdf):
        arr = ArrayObject()
        assert stream.read(1) == "["
        while True:
            # skip leading whitespace
            tok = stream.read(1)
            while tok.isspace():
                tok = stream.read(1)
            stream.seek(-1, 1)
            # check for array ending
            peekahead = stream.read(1)
            if peekahead == "]":
                break
            stream.seek(-1, 1)
            # read and append obj
            arr.append(readObject(stream, pdf))
        return arr
    readFromStream = staticmethod(readFromStream)


class IndirectObject(object):
    def __init__(self, idnum, generation, pdf):
        self.idnum = idnum
        self.generation = generation
        self.pdf = pdf

    def __repr__(self):
        return "IndirectObject(%r, %r)" % (self.idnum, self.generation)

    def writeToStream(self, stream):
        stream.write("%s %s R" % (self.idnum, self.generation))

    def readFromStream(stream, pdf):
        idnum = ""
        while True:
            tok = stream.read(1)
            if tok.isspace():
                break
            idnum += tok
        generation = ""
        while True:
            tok = stream.read(1)
            if tok.isspace():
                break
            generation += tok
        r = stream.read(1)
        #if r != "R":
        #    stream.seek(-20, 1)
        #    print idnum, generation
        #    print repr(stream.read(40))
        assert r == "R"
        return IndirectObject(int(idnum), int(generation), pdf)
    readFromStream = staticmethod(readFromStream)


class FloatObject(float):
    def writeToStream(self, stream):
        stream.write(repr(self))


class NumberObject(int):
    def __init__(self, value):
        int.__init__(self, value)

    def writeToStream(self, stream):
        stream.write(repr(self))

    def readFromStream(stream):
        name = ""
        while True:
            tok = stream.read(1)
            if tok != '+' and tok != '-' and tok != '.' and not tok.isdigit():
                stream.seek(-1, 1)
                break
            name += tok
        if name.find(".") != -1:
            return FloatObject(name)
        else:
            return NumberObject(name)
    readFromStream = staticmethod(readFromStream)


class StringObject(str):
    def writeToStream(self, stream):
        stream.write("(")
        for c in self:
            if not c.isalnum() and not c.isspace():
                stream.write("\\%03o" % ord(c))
            else:
                stream.write(c)
        stream.write(")")

    def readHexStringFromStream(stream):
        stream.read(1)
        txt = ""
        x = ""
        while True:
            tok = readNonWhitespace(stream)
            if tok == ">":
                break
            x += tok
            if len(x) == 2:
                txt += chr(int(x, base=16))
                x = ""
        if len(x) == 1:
            x += "0"
        if len(x) == 2:
            txt += chr(int(x, base=16))
        return StringObject(txt)
    readHexStringFromStream = staticmethod(readHexStringFromStream)

    def readFromStream(stream):
        tok = stream.read(1)
        parens = 1
        txt = ""
        while True:
            tok = stream.read(1)
            if tok == "(":
                parens += 1
            elif tok == ")":
                parens -= 1
                if parens == 0:
                    break
            elif tok == "\\":
                tok = stream.read(1)
                if tok == "n":
                    tok = "\n"
                elif tok == "r":
                    tok = "\r"
                elif tok == "t":
                    tok = "\t"
                elif tok == "b":
                    tok == "\b"
                elif tok == "f":
                    tok = "\f"
                elif tok == "(":
                    tok = "("
                elif tok == ")":
                    tok = ")"
                elif tok == "\\":
                    tok = "\\"
                elif tok.isdigit():
                    tok += stream.read(2)
                    tok = chr(int(tok, base=8))
            txt += tok
        return StringObject(txt)
    readFromStream = staticmethod(readFromStream)


class NameObject(str):
    delimiterCharacters = "(", ")", "<", ">", "[", "]", "{", "}", "/", "%"

    def __init__(self, data):
        str.__init__(self, data)

    def writeToStream(self, stream):
        stream.write(self)

    def readFromStream(stream):
        name = stream.read(1)
        assert name == "/"
        while True:
            tok = stream.read(1)
            if tok.isspace() or tok in NameObject.delimiterCharacters:
                stream.seek(-1, 1)
                break
            name += tok
        return NameObject(name)
    readFromStream = staticmethod(readFromStream)


class DictionaryObject(dict):
    def __init__(self):
        pass

    def writeToStream(self, stream):
        stream.write("<<\n")
        for key, value in self.items():
            if key != "__streamdata__":
                key.writeToStream(stream)
                stream.write(" ")
                value.writeToStream(stream)
                stream.write("\n")
        stream.write(">>")
        if self.has_key("__streamdata__"):
            stream.write("\nstream\n")
            stream.write(self["__streamdata__"])
            stream.write("\nendstream")

    def readFromStream(stream, pdf):
        assert stream.read(2) == "<<"
        retval = DictionaryObject()
        while True:
            tok = readNonWhitespace(stream)
            if tok == ">":
                stream.read(1)
                break
            stream.seek(-1, 1)
            key = readObject(stream, pdf)
            tok = readNonWhitespace(stream)
            stream.seek(-1, 1)
            value = readObject(stream, pdf)
            if retval.has_key(key):
                # multiple definitions of key not handled yet
                assert False
            retval[key] = value
        pos = stream.tell()
        s = readNonWhitespace(stream)
        if s == 's' and stream.read(5) == 'tream':
            eol = stream.read(1)
            assert eol in ("\n", "\r")
            if eol == "\r":
                # read \n after
                stream.read(1)
            # this is a stream object, not a dictionary
            assert retval.has_key("/Length")
            length = retval["/Length"]
            if isinstance(length, IndirectObject):
                t = stream.tell()
                length = pdf.getObject(length)
                stream.seek(t, 0)
            retval["__streamdata__"] = stream.read(length)
            e = readNonWhitespace(stream)
            ndstream = stream.read(8)
            assert e == "e" and ndstream == "ndstream"
        else:
            stream.seek(pos, 0)
        return retval
    readFromStream = staticmethod(readFromStream)

def readObject(stream, pdf):
    tok = stream.read(1)
    stream.seek(-1, 1) # reset to start
    if tok == 't' or tok == 'f':
        # boolean object
        return BooleanObject.readFromStream(stream)
    elif tok == '(':
        # string object
        return StringObject.readFromStream(stream)
    elif tok == '/':
        # name object
        return NameObject.readFromStream(stream)
    elif tok == '[':
        # array object
        return ArrayObject.readFromStream(stream, pdf)
    elif tok == 'n':
        # null object
        return NullObject.readFromStream(stream)
    elif tok == '<':
        # hexadecimal string OR dictionary
        peek = stream.read(2)
        stream.seek(-2, 1) # reset to start
        if peek == '<<':
            return DictionaryObject.readFromStream(stream, pdf)
        else:
            return StringObject.readHexStringFromStream(stream)
    else:
        # number object OR indirect reference
        if tok == '+' or tok == '-':
            # number
            return NumberObject.readFromStream(stream)
        peek = stream.read(20)
        stream.seek(-len(peek), 1) # reset to start
        if re.match(r"(\d+)\s(\d+)\sR", peek) != None:
            return IndirectObject.readFromStream(stream, pdf)
        else:
            return NumberObject.readFromStream(stream)
