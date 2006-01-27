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

import struct
try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

import filters
from generic import *
from utils import readNonWhitespace, readUntilWhitespace
from sets import ImmutableSet

class PdfFileWriter(object):
    def __init__(self):
        self._header = "%PDF-1.3"
        self._objects = []  # array of indirect objects

        # The root of our page tree node.
        pages = DictionaryObject()
        pages.update({
                NameObject("/Type"): NameObject("/Pages"),
                NameObject("/Count"): NumberObject(0),
                NameObject("/Kids"): ArrayObject(),
                })
        self._pages = self._addObject(pages)

        # info object
        info = DictionaryObject()
        info.update({
                NameObject("/Producer"): StringObject("Python PDF Library - http://stompstompstomp.com/pyPdf/")
                })
        self._info = self._addObject(info)

        # root object
        root = DictionaryObject()
        root.update({
            NameObject("/Type"): NameObject("/Catalog"),
            NameObject("/Pages"): self._pages,
            })
        self._root = self._addObject(root)

    def _addObject(self, obj):
        self._objects.append(obj)
        return IndirectObject(len(self._objects), 0, self)

    def _getObject(self, ido):
        assert ido.pdf == self
        return self._objects[ido.idnum - 1]

    def addPage(self, page):
        """
        Adds a page to this PDF file.  A dictionary of /Type = /Page.
        Currently usually aquired from PdfFileReader.getPage().

        Stability: Added in v1.0, will exist for all v1.x releases.
        """
        assert page["/Type"] == "/Page"
        page[NameObject("/Parent")] = self._pages
        page = self._addObject(page)
        pages = self._getObject(self._pages)
        pages["/Kids"].append(page)
        pages["/Count"] = NumberObject(pages["/Count"] + 1)

    def write(self, stream):
        """
        Writes this PDF file to an output stream.  Writes the file as a
        PDF-1.3 format file.

        Stability: Added in v1.0, will exist for all v1.x releases.
        """

        externalReferenceMap = {}
        self.stack = []
        self._sweepIndirectReferences(externalReferenceMap, self._root)
        del self.stack

        # Begin writing:
        object_positions = []
        stream.write(self._header + "\n")
        for i in range(len(self._objects)):
            obj = self._objects[i]
            object_positions.append(stream.tell())
            stream.write(str(i + 1) + " 0 obj\n")
            obj.writeToStream(stream)
            stream.write("\nendobj\n")

        # xref table
        xref_location = stream.tell()
        stream.write("xref\n")
        stream.write("0 %s\n" % (len(self._objects) + 1))
        stream.write("%010d %05d f \n" % (0, 65535))
        for offset in object_positions:
            stream.write("%010d %05d n \n" % (offset, 0))

        # trailer
        stream.write("trailer\n")
        trailer = DictionaryObject()
        trailer.update({
                NameObject("/Size"): NumberObject(len(self._objects) + 1),
                NameObject("/Root"): self._root,
                NameObject("/Info"): self._info,
                })
        trailer.writeToStream(stream)
        
        # eof
        stream.write("\nstartxref\n%s\n%%%%EOF\n" % (xref_location))

    def _sweepIndirectReferences(self, externMap, data):
        if isinstance(data, DictionaryObject):
            for key, value in data.items():
                origvalue = value
                value = self._sweepIndirectReferences(externMap, value)
                if value == None:
                    print objects, value, origvalue
                if hasattr(value, "has_key") and value.has_key("__streamdata__"):
                    # a dictionary value is a stream.  streams must be indirect
                    # objects, so we need to change this value.
                    value = self._addObject(value)
                data[key] = value
            return data
        elif isinstance(data, ArrayObject):
            for i in range(len(data)):
                value = self._sweepIndirectReferences(externMap, data[i])
                if hasattr(value, "has_key") and value.has_key("__streamdata__"):
                    # an array value is a stream.  streams must be indirect
                    # objects, so we need to change this value
                    value = self._addObject(value)
                data[i] = value
            return data
        elif isinstance(data, IndirectObject):
            # internal indirect references are fine
            if data.pdf == self:
                if data.idnum in self.stack:
                    return data
                else:
                    self.stack.append(data.idnum)
                    realdata = self._getObject(data)
                    self._sweepIndirectReferences(externMap, realdata)
                    self.stack.pop()
                    return data
            else:
                newobj = externMap.get(data.pdf, {}).get(data.generation, {}).get(data.idnum, None)
                if newobj == None:
                    newobj = data.pdf.getObject(data)
                    self._objects.append(None) # placeholder
                    idnum = len(self._objects)
                    newobj_ido = IndirectObject(idnum, 0, self)
                    if not externMap.has_key(data.pdf):
                        externMap[data.pdf] = {}
                    if not externMap[data.pdf].has_key(data.generation):
                        externMap[data.pdf][data.generation] = {}
                    externMap[data.pdf][data.generation][data.idnum] = newobj_ido
                    newobj = self._sweepIndirectReferences(externMap, newobj)
                    self._objects[idnum-1] = newobj
                    return newobj_ido
                return newobj
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
            self._flatten()
        return len(self.flattenedPages)

    def getPage(self, pageNumber):
        """
        Retrieves a page by number from this PDF file.  Returns a PageObject
        instance.

        Stability: Added in v1.0, will exist for all v1.x releases.
        """
        # ensure that we're not trying to access an encrypted PDF
        assert not self.trailer.has_key("/Encrypt")
        if self.flattenedPages == None:
            self._flatten()
        return self.flattenedPages[pageNumber]

    def _flatten(self, pages = None, inherit = None):
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
                    inherit[attr] = pages[attr]
            for page in pages["/Kids"]:
                self._flatten(page, inherit)
        elif t == "/Page":
            for attr,value in inherit.items():
                # if the page has it's own value, it does not inherit the
                # parent's value:
                if not pages.has_key(attr):
                    pages[attr] = value
            pageObj = PageObject(self)
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
            streamData = StringIO(filters.decodeStreamData(objStm))
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
        line = ''
        while not line:
            line = self.readNextEndLine(stream)
        assert line[:5] == "%%EOF"

        # find startxref entry - the location of the xref table
        line = self.readNextEndLine(stream)
        startxref = int(line)
        line = self.readNextEndLine(stream)
        assert line[:9] == "startxref"

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
                readNonWhitespace(stream)
                stream.seek(-1, 1)
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
                readNonWhitespace(stream)
                stream.seek(-1, 1)
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
                streamData = StringIO(filters.decodeStreamData(xrefstream))
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
                while x == '\n' or x == '\r':
                    x = stream.read(1)
                    stream.seek(-2, 1)
                stream.seek(1, 1)
                break
            else:
                line = x + line
        return line


def getRectangle(self, name, defaults):
    retval = self.get(name)
    if isinstance(retval, RectangleObject):
        return retval
    if retval == None:
        for d in defaults:
            retval = self.get(d)
            if retval != None:
                break
    if isinstance(retval, IndirectObject):
        retval = self.pdf.getObject(retval)
    retval = RectangleObject(retval)
    setRectangle(self, name, retval)
    return retval

def setRectangle(self, name, value):
    if not isinstance(name, NameObject):
        name = NameObject(name)
    self[name] = value

def deleteRectangle(self, name):
    del self[name]

def addRectangleAccessor(klass, propname, name, fallback, docs):
    setattr(klass, propname,
        property(
            lambda self: getRectangle(self, name, fallback),
            lambda self, value: setRectangle(self, name, value),
            lambda self: deleteRectangle(self, name),
            docs
            )
        )

class PageObject(DictionaryObject):
    def __init__(self, pdf):
        self.pdf = pdf

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

    def __mergeResources(res1, res2, resource):
        newRes = DictionaryObject()
        newRes.update(res1.get(resource, DictionaryObject()).getObject())
        page2Res = res2.get(resource, DictionaryObject()).getObject()
        renameRes = {}
        for key in page2Res.keys():
            if newRes.has_key(key) and newRes[key] != page2Res[key]:
                newname = NameObject(key + "_renamed")
                renameRes[key] = newname
                newRes[newname] = page2Res[key]
            elif not newRes.has_key(key):
                newRes[key] = page2Res[key]
        return newRes, renameRes
    __mergeResources = staticmethod(__mergeResources)

    def mergePage(self, page2):
        """
        Merges the content streams of two pages into one.

        Stability: Added in v1.4, will exist for all v1.x releases thereafter.
        """
        newContentArray = ArrayObject()

        originalContent = self["/Contents"].getObject()
        if isinstance(originalContent, ArrayObject):
            newContentArray.extend(originalContent)
        else:
            newContentArray.append(originalContent)

        page2Content = page2['/Contents'].getObject()
        if isinstance(page2Content, ArrayObject):
            newContentArray.extend(page2Content)
        else:
            newContentArray.append(page2Content)

        newResources = DictionaryObject()

        originalResources = self["/Resources"].getObject()
        page2Resources = page2["/Resources"].getObject()

        newFonts, renameFonts = PageObject.__mergeResources(originalResources, page2Resources, "/Font")
        newResources[NameObject("/Font")] = newFonts
        newGS, renameGS = PageObject.__mergeResources(originalResources, page2Resources, "/ExtGState")
        newResources[NameObject("/ExtGState")] = newGS

        newResources[NameObject("/ProcSet")] = ArrayObject(
            ImmutableSet(originalResources.get("/ProcSet", ArrayObject()).getObject()).union(
                ImmutableSet(page2Resources.get("/ProcSet", ArrayObject()).getObject())
            )
        )

        self[NameObject('/Contents')] = newContentArray
        self[NameObject('/Resources')] = newResources

addRectangleAccessor(PageObject, "mediaBox", "/MediaBox", (),
        """A rectangle, expressed in default user space units, defining the
        boundaries of the physical medium on which the page is intended to be
        displayed or printed.

        Stability: Added in v1.4, will exist for all v1.x releases
        thereafter.""")
addRectangleAccessor(PageObject, "cropBox", "/CropBox", ("/MediaBox",),
        """A rectangle, expressed in default user space units, defining the
        visible region of default user space.  When the page is displayed or
        printed, its contents are to be clipped (cropped) to this rectangle and
        then imposed on the output medium in some implementation-defined
        manner.  Default value: same as MediaBox.

        Stability: Added in v1.4, will exist for all v1.x releases
        thereafter.""")
addRectangleAccessor(PageObject, "bleedBox", "/BleedBox", ("/CropBox",
        "/MediaBox"), """A rectangle, expressed in default user space units,
        defining the region to which the contents of the page should be clipped
        when output in a production environment.
        
        Stability: Added in v1.4, will exist for all v1.x releases
        thereafter.""")
addRectangleAccessor(PageObject, "trimBox", "/TrimBox", ("/CropBox",
        "/MediaBox"), """A rectangle, expressed in default user space units,
        defining the intended dimensions of the finished page after trimming.
        
        Stability: Added in v1.4, will exist for all v1.x releases
        thereafter.""")
addRectangleAccessor(PageObject, "artBox", "/ArtBox", ("/CropBox",
        "/MediaBox"), """A rectangle, expressed in default user space units,
        defining the extent of the page's meaningful content as intended by the
        page's creator.
        
        Stability: Added in v1.4, will exist for all v1.x releases
        thereafter.""")


class ContentStream(DictionaryObject):
    def __init__(self, stream):
        self.operations = []
        self.__parseContentStream(stream)

    def __parseContentStream(self, stream):
        stream = StringIO(filters.decodeStreamData(stream))
        operands = []
        while True:
            peek = readNonWhitespace(stream)
            if peek == '':
                break
            stream.seek(-1, 1)
            if peek.isalpha():
                operator = readUntilWhitespace(stream)
                self.operations.append((operands, operator))
                operands = []
                print self.operations[-1]
            else:
                operands.append(readObject(stream, None))


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

    input1 = PdfFileReader(file("..\\test\\PDFReference16.pdf", "rb"))
    page1 = input1.getPage(0)
    page2 = input1.getPage(1)
    page3 = input1.getPage(2)
    page1.mergePage(page2)
    page1.mergePage(page3)
    output.addPage(page1)

    output.write(file("test.pdf", "wb"))


