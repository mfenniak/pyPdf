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
A pure-Python PDF library with very minimal capabilities.  It was designed to
be able to split and merge PDF files by page, and that's about all it can do.
It may be a solid base for future PDF file work in Python.
"""
__author__ = "Mathieu Fenniak"
__author_email__ = "mfenniak@pobox.com"

import re
import struct
import zlib
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


class PdfFileWriter(object):
    def __init__(self):
        self.header = "%PDF-1.3"
        self.pages = []

    def addPage(self, page):
        """
        Adds a page to this PDF file.  A dictionary of /Type = /Page.
        Currently usually aquired from PdfFileReader.getPage().

        Stability: Added in v1.0, will exist for all v1.x releases.
        """
        self.pages.append(page)

    def write(self, stream):
        """
        Writes this PDF file to an output stream.  Writes the file as a
        PDF-1.3 format file.

        Stability: Added in v1.0, will exist for all v1.x releases.
        """
        objects = []

        # The pages will all have a new parent, so we need to replace their
        # existing parent object.
        pages = DictionaryObject()
        pages.update({
                NameObject("/Type"): NameObject("/Pages"),
                NameObject("/Count"): NumberObject(len(self.pages)),
                NameObject("/Kids"): ArrayObject(),
                })
        objects.append(pages)
        pages_ido = IndirectObject(len(objects), 0, self)
        for page in self.pages:
            page[NameObject("/Parent")] = pages_ido

        # info object
        info = DictionaryObject()
        info.update({
                NameObject("/Producer"): StringObject("Python PDF Library - mfenniak@pobox.com")
                })
        objects.append(info)
        info = IndirectObject(len(objects), 0, self)

        # root object
        root = DictionaryObject()
        root.update({
            NameObject("/Type"): NameObject("/Catalog"),
            NameObject("/Pages"): pages_ido,
            })
        objects.append(root)
        root = IndirectObject(len(objects), 0, self)

        # The real work.  Find any indirect references in out pages,
        # and make them into objects for us to write.
        externalReferenceMap = {}
        for page in self.pages:
            page = self.sweepIndirectReferences(externalReferenceMap, objects, page)
            objects.append(page)
            pages["/Kids"].append(IndirectObject(len(objects), 0, self))

        # Begin writing:
        stream.write(self.header + "\n")
        for i in range(len(objects)):
            obj = objects[i]
            objects[i] = stream.tell()
            stream.write(str(i + 1) + " 0 obj\n")
            obj.writeToStream(stream)
            stream.write("\nendobj\n")

        # xref table
        xref_location = stream.tell()
        stream.write("xref\n")
        stream.write("0 %s\n" % (len(objects) + 1))
        stream.write("%010d %05d f \n" % (0, 65535))
        for offset in objects:
            stream.write("%010d %05d n \n" % (offset, 0))

        # trailer
        stream.write("trailer\n")
        trailer = DictionaryObject()
        trailer.update({
                NameObject("/Size"): NumberObject(len(objects) + 1),
                NameObject("/Root"): root,
                NameObject("/Info"): info,
                })
        trailer.writeToStream(stream)
        
        # eof
        stream.write("\nstartxref\n%s\n%%%%EOF\n" % (xref_location))

    def sweepIndirectReferences(self, externMap, objects, data):
        if isinstance(data, DictionaryObject):
            for key, value in data.items():
                origvalue = value
                value = self.sweepIndirectReferences(externMap, objects, value)
                if value == None:
                    print objects, value, origvalue
                data[key] = value
            return data
        elif isinstance(data, ArrayObject):
            for i in range(len(data)):
                data[i] = self.sweepIndirectReferences(externMap, objects, data[i])
            return data
        elif isinstance(data, IndirectObject):
            # internal indirect references are fine
            if data.pdf != self:
                newobj = externMap.get(data.pdf, {}).get(data.generation, {}).get(data.idnum, None)
                if newobj == None:
                    newobj = data.pdf.getObject(data)
                    objects.append(None) # placeholder
                    idnum = len(objects)
                    newobj_ido = IndirectObject(idnum, 0, self)
                    if not externMap.has_key(data.pdf):
                        externMap[data.pdf] = {}
                    if not externMap[data.pdf].has_key(data.generation):
                        externMap[data.pdf][data.generation] = {}
                    externMap[data.pdf][data.generation][data.idnum] = newobj_ido
                    newobj = self.sweepIndirectReferences(externMap, objects, newobj)
                    objects[idnum-1] = newobj
                    return newobj_ido
                return newobj
            else:
                return data
        else:
            return data


class PdfFileReader(object):
    def __init__(self, stream):
        """
        Initializes a PdfFileReader object.  This operation can take some time,
        as the PDF file cross-reference tables are read.  "stream" parameter
        must be a data stream, not a string or a path name.

        Stability: Added in v1.0, will exist for all v1.x releases.
        """
        self.flattenedPages = None
        self.resolvedObjects = {}
        self.read(stream)
        self.stream = stream

    def getNumPages(self):
        """
        Returns the number of pages in this PDF file.

        Stability: Added in v1.0, will exist for all v1.x releases.
        """
        if self.flattenedPages == None:
            self.flatten()
        return len(self.flattenedPages)

    def getPage(self, pageNumber):
        """
        Retrieves a page by number from this PDF file.  Returns a PageObject
        instance.

        Stability: Added in v1.0, will exist for all v1.x releases.
        """
        if self.flattenedPages == None:
            self.flatten()
        return self.flattenedPages[pageNumber]

    def flatten(self, pages = None, inherit = None):
        inheritablePageAttributes = (
            NameObject("/Resources"), NameObject("/MediaBox"),
            NameObject("/CropBox"), NameObject("/Rotate")
            )
        if inherit == None:
            inherit = dict()
        if pages == None:
            self.flattenedPages = []
            catalog = self.getObject(self.trailer["/Root"])
            pages = self.getObject(catalog["/Pages"])
        if isinstance(pages, IndirectObject):
            pages = self.getObject(pages)
        t = pages["/Type"]
        if t == "/Pages":
            for attr in inheritablePageAttributes:
                if pages.has_key(attr):
                    inherit[attr] = t[attr]
            for page in pages["/Kids"]:
                self.flatten(page, inherit)
        elif t == "/Page":
            for attr,value in inherit.items():
                # if the page has it's own value, it does not inherit the
                # parent's value:
                if not pages.has_key(attr):
                    pages[attr] = value
            pageObj = PageObject()
            pageObj.update(pages)
            self.flattenedPages.append(pageObj)

    def getObject(self, indirectReference):
        retval = self.resolvedObjects.get(indirectReference.generation, {}).get(indirectReference.idnum, None)
        if retval != None:
            return retval
        if indirectReference.generation == 0 and \
           self.xref_objStm.has_key(indirectReference.idnum):
            # indirect reference to object in object stream
            # read the entire object stream into memory
            stmnum,idx = self.xref_objStm[indirectReference.idnum]
            objStm = self.getObject(IndirectObject(stmnum, 0, self))
            assert objStm['/Type'] == '/ObjStm'
            assert idx < objStm['/N']
            streamData = StringIO(decodeStreamData(objStm))
            for i in range(objStm['/N']):
                objnum = NumberObject.readFromStream(streamData)
                readNonWhitespace(streamData)
                streamData.seek(-1, 1)
                offset = NumberObject.readFromStream(streamData)
                readNonWhitespace(streamData)
                streamData.seek(-1, 1)
                t = streamData.tell()
                streamData.seek(objStm['/First']+offset, 0)
                obj = readObject(streamData, self)
                self.resolvedObjects[0][objnum] = obj
                streamData.seek(t, 0)
            return self.resolvedObjects[0][indirectReference.idnum]
        start = self.xref[indirectReference.generation][indirectReference.idnum]
        self.stream.seek(start, 0)
        idnum, generation = self.readObjectHeader(self.stream)
        assert idnum == indirectReference.idnum
        assert generation == indirectReference.generation
        retval = readObject(self.stream, self)
        self.cacheIndirectObject(generation, idnum, retval)
        return retval

    def readObjectHeader(self, stream):
        idnum = readUntilWhitespace(stream)
        generation = readUntilWhitespace(stream)
        obj = stream.read(3)
        readNonWhitespace(stream)
        stream.seek(-1, 1)
        return int(idnum), int(generation)

    def cacheIndirectObject(self, generation, idnum, obj):
        if not self.resolvedObjects.has_key(generation):
            self.resolvedObjects[generation] = {}
        self.resolvedObjects[generation][idnum] = obj

    def read(self, stream):
        # start at the end:
        stream.seek(-2, 2)
        line = self.readNextEndLine(stream)
        assert line == "%%EOF"

        # find startxref entry - the location of the xref table
        line = self.readNextEndLine(stream)
        startxref = int(line)
        line = self.readNextEndLine(stream)
        assert line == "startxref"

        # read all cross reference tables and their trailers
        self.xref = {}
        self.xref_objStm = {}
        self.trailer = {}
        while 1:
            # load the xref table
            stream.seek(startxref, 0)
            x = stream.read(1)
            if x == "x":
                # standard cross-reference table
                ref = stream.read(4)
                assert ref[:3] == "ref"
                num = readObject(stream, self)
                readNonWhitespace(stream)
                stream.seek(-1, 1)
                size = readObject(stream, self)
                readNonWhitespace(stream)
                stream.seek(-1, 1)
                cnt = 0
                while cnt < size:
                    line = stream.readline()
                    offset, generation = line[:16].split(" ")
                    offset, generation = int(offset), int(generation)
                    if not self.xref.has_key(generation):
                        self.xref[generation] = {}
                    self.xref[generation][num] = offset
                    cnt += 1
                    num += 1
                assert stream.read(7) == "trailer"
                readNonWhitespace(stream)
                stream.seek(-1, 1)
                newTrailer = readObject(stream, self)
                for key, value in newTrailer.items():
                    if not self.trailer.has_key(key):
                        self.trailer[key] = value
                if newTrailer.has_key(NameObject("/Prev")):
                    startxref = newTrailer[NameObject("/Prev")]
                else:
                    break
            else:
                # PDF 1.5+ Cross-Reference Stream
                stream.seek(-1, 1)
                idnum, generation = self.readObjectHeader(stream)
                xrefstream = readObject(stream, self)
                assert xrefstream["/Type"] == "/XRef"
                self.cacheIndirectObject(generation, idnum, xrefstream)
                streamData = StringIO(decodeStreamData(xrefstream))
                num, size = xrefstream.get("/Index", [0, xrefstream.get("/Size")])
                entrySizes = xrefstream.get("/W")
                cnt = 0
                while cnt < size:
                    for i in range(len(entrySizes)):
                        d = streamData.read(entrySizes[i])
                        di = convertToInt(d, entrySizes[i])
                        if i == 0:
                            xref_type = di
                        elif i == 1:
                            if xref_type == 0:
                                next_free_object = di
                            elif xref_type == 1:
                                byte_offset = di
                            elif xref_type == 2:
                                objstr_num = di
                        elif i == 2:
                            if xref_type == 0:
                                next_generation = di
                            elif xref_type == 1:
                                generation = di
                            elif xref_type == 2:
                                obstr_idx = di
                    if xref_type == 0:
                        pass
                    elif xref_type == 1:
                        if not self.xref.has_key(generation):
                            self.xref[generation] = {}
                        self.xref[generation][num] = byte_offset
                    elif xref_type == 2:
                        self.xref_objStm[num] = [objstr_num, obstr_idx]
                    cnt += 1
                    num += 1
                trailerKeys = "/Root", "/Encrypt", "/Info", "/ID"
                for key in trailerKeys:
                    if xrefstream.has_key(key) and not self.trailer.has_key(key):
                        self.trailer[NameObject(key)] = xrefstream[key]
                if xrefstream.has_key("/Prev"):
                    startxref = xrefstream["/Prev"]
                else:
                    break

    def readNextEndLine(self, stream):
        line = ""
        while True:
            x = stream.read(1)
            stream.seek(-2, 1)
            if x == '\n' or x == '\r':
                break
            else:
                line = x + line
        return line


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


class PageObject(DictionaryObject):
    def rotateClockwise(self, angle):
        """
        Rotates a page clockwise by increments of 90 degrees.

        Stability: Added in v1.1, will exist for all v1.x releases thereafter.
        """
        assert angle % 90 == 0
        self.__rotate(angle)
        return self

    def rotateCounterClockwise(self, angle):
        """
        Rotates a page counter-clockwise by increments of 90 degrees.  Note
        that this is equivilant to calling rotateClockwise(-angle).

        Stability: Added in v1.1, will exist for all v1.x releases thereafter.
        """
        assert angle % 90 == 0
        self.__rotate(-angle)
        return self

    def __rotate(self, angle):
        currentAngle = self.get("/Rotate", 0)
        self[NameObject("/Rotate")] = NumberObject(currentAngle + angle)


def readUntilWhitespace(stream):
    txt = ""
    while True:
        tok = stream.read(1)
        if tok.isspace():
            break
        txt += tok
    return txt

def readNonWhitespace(stream):
    tok = ' '
    while tok == '\n' or tok == '\r' or tok == ' ' or tok == '\t':
        tok = stream.read(1)
    return tok

def decodeStreamData(stream):
    if stream.get("/Filter",None) == "/FlateDecode":
        data = zlib.decompress(stream["__streamdata__"])
    else:
        # unsupported Filter
        assert False
    predictor = stream.get("/DecodeParms", {}).get("/Predictor", 1)
    if predictor != 1:
        columns = stream["/DecodeParms"]["/Columns"]
        if predictor >= 10:
            newdata = ""
            # PNG prediction can vary from row to row
            rowlength = columns + 1
            assert len(data) % rowlength == 0
            prev_rowdata = "\x00"*rowlength
            for row in range(len(data) / rowlength):
                rowdata = list(data[(row*rowlength):((row+1)*rowlength)])
                filterByte = ord(rowdata[0])
                if filterByte == 0:
                    pass
                elif filterByte == 1:
                    for i in range(2, rowlength):
                        rowdata[i] = chr((ord(rowdata[i]) + ord(rowdata[i-1])) % 256)
                elif filterByte == 2:
                    for i in range(1, rowlength):
                        rowdata[i] = chr((ord(rowdata[i]) + ord(prev_rowdata[i])) % 256)
                else:
                    # unsupported PNG filter
                    assert False
                prev_rowdata = rowdata
                newdata += ''.join(rowdata[1:])
            data = newdata
        else:
            # unsupported predictor
            assert False
    return data

def convertToInt(d, size):
    if size <= 4:
        d = "\x00\x00\x00\x00" + d
        d = d[-4:]
        return struct.unpack(">l", d)[0]
    elif size <= 8:
        d = "\x00\x00\x00\x00\x00\x00\x00\x00" + d
        d = d[-8:]
        return struct.unpack(">q", d)[0]
    else:
        # size too big
        assert False


if __name__ == "__main__":
    output = PdfFileWriter()

    #input1 = PdfFileReader(file("cc-cc.pdf", "rb"))
    #output.addPage(input1.getPage(0))

    input2 = PdfFileReader(file("PDFReference16.pdf", "rb"))
    for i in range(input2.getNumPages()):
        output.addPage(input2.getPage(i))
    
    output.write(file("test.pdf", "wb"))

