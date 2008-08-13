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
__author_email__ = "biziqe@mathieu.fenniak.net"

import re
from .utils import (readNonWhitespace, RC4_encrypt, PdfReadError)
from .filters import (FlateDecode, decodeStreamData)
import decimal
import codecs

def readObject(stream, pdf):
    tok = stream.read(1)
    stream.seek(-1, 1) # reset to start
    if tok == b't' or tok == b'f':
        # boolean object
        return BooleanObject.readFromStream(stream)
    elif tok == b'(':
        # string object
        return readStringFromStream(stream)
    elif tok == b'/':
        # name object
        return NameObject.readFromStream(stream)
    elif tok == b'[':
        # array object
        return ArrayObject.readFromStream(stream, pdf)
    elif tok == b'n':
        # null object
        return NullObject.readFromStream(stream)
    elif tok == b'<':
        # hexadecimal string OR dictionary
        peek = stream.read(2)
        stream.seek(-2, 1) # reset to start
        if peek == b'<<':
            return DictionaryObject.readFromStream(stream, pdf)
        else:
            return readHexStringFromStream(stream)
    elif tok == b'%':
        # comment
        while tok not in (b'\r', b'\n'):
            tok = stream.read(1)
        tok = readNonWhitespace(stream)
        stream.seek(-1, 1)
        return readObject(stream, pdf)
    else:
        # number object OR indirect reference
        if tok == b'+' or tok == b'-':
            # number
            return NumberObject.readFromStream(stream)
        peek = stream.read(20)
        stream.seek(-len(peek), 1) # reset to start
        if re.match(r"(\d+)\s(\d+)\sR[^a-zA-Z]", peek) != None:
            return IndirectObject.readFromStream(stream, pdf)
        else:
            return NumberObject.readFromStream(stream)

class PdfObject(object):
    def getObject(self):
        """Resolves indirect references."""
        return self


class NullObject(PdfObject):
    def writeToStream(self, stream, encryption_key):
        stream.write(b"null")

    def readFromStream(stream):
        nulltxt = stream.read(4)
        if nulltxt != b"null":
            raise PdfReadError("error reading null object")
        return NullObject()
    readFromStream = staticmethod(readFromStream)


class BooleanObject(PdfObject):
    def __init__(self, value):
        self.value = value

    def writeToStream(self, stream, encryption_key):
        if self.value:
            stream.write(b"true")
        else:
            stream.write(b"false")

    def readFromStream(stream):
        word = stream.read(4)
        if word == b"true":
            return BooleanObject(True)
        elif word == b"fals":
            stream.read(1)
            return BooleanObject(False)
        assert False
    readFromStream = staticmethod(readFromStream)


class ArrayObject(list, PdfObject):
    def writeToStream(self, stream, encryption_key):
        stream.write(b"[")
        for data in self:
            stream.write(b" ")
            data.writeToStream(stream, encryption_key)
        stream.write(b" ]")

    def readFromStream(stream, pdf):
        arr = ArrayObject()
        tmp = stream.read(1)
        if tmp != b"[":
            raise PdfReadError("error reading array")
        while True:
            # skip leading whitespace
            tok = stream.read(1)
            while tok in b" \t\n\r":
                tok = stream.read(1)
            stream.seek(-1, 1)
            # check for array ending
            peekahead = stream.read(1)
            if peekahead == b"]":
                break
            stream.seek(-1, 1)
            # read and append obj
            obj = readObject(stream, pdf)
            arr.append(obj)
        return arr
    readFromStream = staticmethod(readFromStream)


class IndirectObject(PdfObject):
    def __init__(self, idnum, generation, pdf):
        self.idnum = idnum
        self.generation = generation
        self.pdf = pdf

    def getObject(self):
        return self.pdf.getObject(self).getObject()

    def __repr__(self):
        return "IndirectObject(%r, %r)" % (self.idnum, self.generation)

    def __eq__(self, other):
        return (
            other != None and
            isinstance(other, IndirectObject) and
            self.idnum == other.idnum and
            self.generation == other.generation and
            self.pdf is other.pdf
            )

    def __ne__(self, other):
        return not self.__eq__(other)

    def writeToStream(self, stream, encryption_key):
        stream.write(("%s %s R" % (self.idnum, self.generation)).encode("ascii"))

    def readFromStream(stream, pdf):
        idnum = b""
        while True:
            tok = stream.read(1)
            if tok in b" \t\n\r":
                break
            idnum += tok
        generation = b""
        while True:
            tok = stream.read(1)
            if tok in b" \t\n\r":
                break
            generation += tok
        r = stream.read(1)
        if r != b"R":
            raise utils.PdfReadError("error reading indirect object reference")
        return IndirectObject(int(idnum), int(generation), pdf)
    readFromStream = staticmethod(readFromStream)


class FloatObject(decimal.Decimal, PdfObject):
    def __new__(cls, value="0", context=None):
        return decimal.Decimal.__new__(cls, str(value), context)
    def __repr__(self):
        return str(self)
    def writeToStream(self, stream, encryption_key):
        stream.write(str(self).encode("ascii"))


class NumberObject(int, PdfObject):
    def writeToStream(self, stream, encryption_key):
        stream.write(repr(self).encode("ascii"))

    def readFromStream(stream):
        name = b""
        while True:
            tok = stream.read(1)
            if tok != b'+' and tok != b'-' and tok != b'.' and not tok in b'0123456789':
                stream.seek(-1, 1)
                break
            name += tok
        if name.find(b".") != -1:
            return FloatObject(name.decode("ascii"))
        else:
            return NumberObject(name)
    readFromStream = staticmethod(readFromStream)


##
# Given a string (either a "str" or "unicode"), create a ByteStringObject or a
# TextStringObject to represent the string.
def createStringObject(string):
    if isinstance(string, str):
        return TextStringObject(string)
    elif isinstance(string, bytes):
        if string.startswith(codecs.BOM_UTF16_BE):
            retval = TextStringObject(string.decode("utf-16"))
            retval.autodetect_utf16 = True
            return retval
        else:
            # This is probably a big performance hit here, but we need to
            # convert string objects into the text/unicode-aware version if
            # possible... and the only way to check if that's possible is
            # to try.  Some strings are strings, some are just byte arrays.
            try:
                retval = TextStringObject(decode_pdfdocencoding(string))
                retval.autodetect_pdfdocencoding = True
                return retval
            except UnicodeDecodeError:
                return ByteStringObject(string)
    else:
        raise TypeError("createStringObject should have str or unicode arg")


def readHexStringFromStream(stream):
    stream.read(1)
    txt = b""
    x = b""
    while True:
        tok = readNonWhitespace(stream)
        if tok == b">":
            break
        x += tok
        if len(x) == 2:
            txt += bytes.fromhex(x.decode("ascii"))
            x = b""
    if len(x) == 1:
        x += b"0"
    if len(x) == 2:
        txt += bytes.fromhex(x)
    return createStringObject(txt)


def readStringFromStream(stream):
    tok = stream.read(1)
    parens = 1
    txt = b""
    while True:
        tok = stream.read(1)
        if tok == b"(":
            parens += 1
        elif tok == b")":
            parens -= 1
            if parens == 0:
                break
        elif tok == b"\\":
            tok = stream.read(1)
            if tok == b"n":
                tok = b"\n"
            elif tok == b"r":
                tok = b"\r"
            elif tok == b"t":
                tok = "\t"
            elif tok == b"b":
                tok = b"\b"
            elif tok == b"f":
                tok = b"\f"
            elif tok == b"(":
                tok = b"("
            elif tok == b")":
                tok = b")"
            elif tok == b"\\":
                tok = b"\\"
            elif tok in b"0123456789":
                # Note: PDF spec says that octal characters don't need to
                # provide 3 numbers.  Not supported here.
                tok += stream.read(2)
                tok = bytes([int(tok, base=8)])
            elif tok in b"\n\r":
                # This case is  hit when a backslash followed by a line
                # break occurs.  If it's a multi-char EOL, consume the
                # second character:
                tok = stream.read(1)
                if not tok in b"\n\r":
                    stream.seek(-1, 1)
                # Then don't add anything to the actual string, since this
                # line break was escaped:
                tok = b''
            else:
                raise utils.PdfReadError("Unexpected escaped string")
        txt += tok
    return createStringObject(txt)


##
# Represents a string object where the text encoding could not be determined.
# This occurs quite often, as the PDF spec doesn't provide an alternate way to
# represent strings -- for example, the encryption data stored in files (like
# /O) is clearly not text, but is still stored in a "String" object.
class ByteStringObject(bytes, PdfObject):

    ##
    # For compatibility with TextStringObject.original_bytes.  This method
    # returns self.
    original_bytes = property(lambda self: self)

    def writeToStream(self, stream, encryption_key):
        bytearr = self
        if encryption_key:
            bytearr = RC4_encrypt(encryption_key, bytearr)
        stream.write(b"<")
        for b in self:
            stream.write(("%.2x" % b).encode("ascii"))
        stream.write(b">")


##
# Represents a string object that has been decoded into a real unicode string.
# If read from a PDF document, this string appeared to match the
# PDFDocEncoding, or contained a UTF-16BE BOM mark to cause UTF-16 decoding to
# occur.
class TextStringObject(str, PdfObject):
    autodetect_pdfdocencoding = False
    autodetect_utf16 = False

    ##
    # It is occasionally possible that a text string object gets created where
    # a byte string object was expected due to the autodetection mechanism --
    # if that occurs, this "original_bytes" property can be used to
    # back-calculate what the original encoded bytes were.
    original_bytes = property(lambda self: self.get_original_bytes())

    def get_original_bytes(self):
        # We're a text string object, but the library is trying to get our raw
        # bytes.  This can happen if we auto-detected this string as text, but
        # we were wrong.  It's pretty common.  Return the original bytes that
        # would have been used to create this object, based upon the autodetect
        # method.
        if self.autodetect_utf16:
            return codecs.BOM_UTF16_BE + self.encode("utf-16be")
        elif self.autodetect_pdfdocencoding:
            return encode_pdfdocencoding(self)
        else:
            raise Exception("no information about original bytes")

    def writeToStream(self, stream, encryption_key):
        # Try to write the string out as a PDFDocEncoding encoded string.  It's
        # nicer to look at in the PDF file.  Sadly, we take a performance hit
        # here for trying...
        try:
            bytearr = encode_pdfdocencoding(self)
        except UnicodeEncodeError:
            bytearr = codecs.BOM_UTF16_BE + self.encode("utf-16be")
        if encryption_key:
            bytearr = RC4_encrypt(encryption_key, bytearr)
            obj = ByteStringObject(bytearr)
            obj.writeToStream(stream, None)
        else:
            stream.write(b"(")
            for c in bytearr:
                if (c == 32) or (65 <= c <= 90) or (97 <= c <= 122):
                    stream.write(bytes((c,)))
                else:
                    stream.write(("\\%03o" % c).encode("ascii"))
            stream.write(b")")


class NameObject(str, PdfObject):
    delimiterCharacters = b"()<>[]{}/%"

    def writeToStream(self, stream, encryption_key):
        stream.write(self.encode("ascii"))

    def readFromStream(stream):
        name = stream.read(1)
        if name != b"/":
            raise PdfReadError("name read error")
        while True:
            tok = stream.read(1)
            if (tok in b" \t\n\r") or (tok in NameObject.delimiterCharacters):
                stream.seek(-1, 1)
                break
            name += tok
        name = name.decode("ascii")
        return NameObject(name)
    readFromStream = staticmethod(readFromStream)


class DictionaryObject(dict, PdfObject):

    def __init__(self, *args, **kwargs):
        if len(args) == 0:
            self.update(kwargs)
        elif len(args) == 1:
            arr = args[0]
            # If we're passed a list/tuple, make a dict out of it
            if not hasattr(arr, "items"):
                newarr = {}
                for k, v in arr:
                    newarr[k] = v
                arr = newarr
            self.update(arr)
        else:
            raise TypeError("dict expected at most 1 argument, got 3")

    def update(self, arr):
        # note, a ValueError halfway through copying values
        # will leave half the values in this dict.
        for k, v in arr.items():
            self.__setitem__(k, v)

    def raw_get(self, key):
        return dict.__getitem__(self, key)

    def __setitem__(self, key, value):
        if not isinstance(key, PdfObject):
            raise ValueError("key must be PdfObject")
        if not isinstance(value, PdfObject):
            raise ValueError("value must be PdfObject")
        return dict.__setitem__(self, key, value)

    def setdefault(self, key, value=None):
        if not isinstance(key, PdfObject):
            raise ValueError("key must be PdfObject")
        if not isinstance(value, PdfObject):
            raise ValueError("value must be PdfObject")
        return dict.setdefault(self, key, value)

    def __getitem__(self, key):
        return dict.__getitem__(self, key).getObject()

    ##
    # Retrieves XMP (Extensible Metadata Platform) data relevant to the
    # this object, if available.
    # <p>
    # Stability: Added in v1.12, will exist for all future v1.x releases.
    # @return Returns a {@link #xmp.XmpInformation XmlInformation} instance
    # that can be used to access XMP metadata from the document.  Can also
    # return None if no metadata was found on the document root.
    def getXmpMetadata(self):
        metadata = self.get("/Metadata", None)
        if metadata == None:
            return None
        metadata = metadata.getObject()
        import xmp
        if not isinstance(metadata, xmp.XmpInformation):
            metadata = xmp.XmpInformation(metadata)
            self[NameObject("/Metadata")] = metadata
        return metadata

    ##
    # Read-only property that accesses the {@link
    # #DictionaryObject.getXmpData getXmpData} function.
    # <p>
    # Stability: Added in v1.12, will exist for all future v1.x releases.
    xmpMetadata = property(lambda self: self.getXmpMetadata(), None, None)

    def writeToStream(self, stream, encryption_key):
        stream.write(b"<<\n")
        for key, value in list(self.items()):
            key.writeToStream(stream, encryption_key)
            stream.write(b" ")
            value.writeToStream(stream, encryption_key)
            stream.write(b"\n")
        stream.write(b">>")

    def readFromStream(stream, pdf):
        tmp = stream.read(2)
        if tmp != b"<<":
            raise PdfReadError("dictionary read error")
        data = {}
        while True:
            tok = readNonWhitespace(stream)
            if tok == b">":
                stream.read(1)
                break
            stream.seek(-1, 1)
            key = readObject(stream, pdf)
            tok = readNonWhitespace(stream)
            stream.seek(-1, 1)
            value = readObject(stream, pdf)
            if key in data:
                # multiple definitions of key not permitted
                raise PdfReadError("multiple definitions in dictionary")
            data[key] = value
        pos = stream.tell()
        s = readNonWhitespace(stream)
        if s == b's' and stream.read(5) == b'tream':
            eol = stream.read(1)
            # odd PDF file output has spaces after 'stream' keyword but before EOL.
            # patch provided by Danial Sandler
            while eol == b' ':
                eol = stream.read(1)
            assert eol in (b"\n", b"\r")
            if eol == b"\r":
                # read \n after
                stream.read(1)
            # this is a stream object, not a dictionary
            assert "/Length" in data
            length = data["/Length"]
            if isinstance(length, IndirectObject):
                t = stream.tell()
                length = pdf.getObject(length)
                stream.seek(t, 0)
            data["__streamdata__"] = stream.read(length)
            e = readNonWhitespace(stream)
            ndstream = stream.read(8)
            if (e + ndstream) != b"endstream":
                # (sigh) - the odd PDF file has a length that is too long, so
                # we need to read backwards to find the "endstream" ending.
                # ReportLab (unknown version) generates files with this bug,
                # and Python users into PDF files tend to be our audience.
                # we need to do this to correct the streamdata and chop off
                # an extra character.
                pos = stream.tell()
                stream.seek(-10, 1)
                end = stream.read(9)
                if end == b"endstream":
                    # we found it by looking back one character further.
                    data["__streamdata__"] = data["__streamdata__"][:-1]
                else:
                    stream.seek(pos, 0)
                    raise PdfReadError("Unable to find 'endstream' marker after stream.")
        else:
            stream.seek(pos, 0)
        if "__streamdata__" in data:
            return StreamObject.initializeFromDictionary(data)
        else:
            retval = DictionaryObject()
            retval.update(data)
            return retval
    readFromStream = staticmethod(readFromStream)


class StreamObject(DictionaryObject):
    def __init__(self):
        self._data = None
        self.decodedSelf = None

    def writeToStream(self, stream, encryption_key):
        self[NameObject("/Length")] = NumberObject(len(self._data))
        DictionaryObject.writeToStream(self, stream, encryption_key)
        del self["/Length"]
        stream.write(b"\nstream\n")
        data = self._data
        if encryption_key:
            data = RC4_encrypt(encryption_key, data)
        stream.write(data)
        stream.write(b"\nendstream")

    def initializeFromDictionary(data):
        if "/Filter" in data:
            retval = EncodedStreamObject()
        else:
            retval = DecodedStreamObject()
        retval._data = data["__streamdata__"]
        del data["__streamdata__"]
        del data["/Length"]
        retval.update(data)
        return retval
    initializeFromDictionary = staticmethod(initializeFromDictionary)

    def flateEncode(self):
        if "/Filter" in self:
            f = self["/Filter"]
            if isinstance(f, ArrayObject):
                f.insert(0, NameObject("/FlateDecode"))
            else:
                newf = ArrayObject()
                newf.append(NameObject("/FlateDecode"))
                newf.append(f)
                f = newf
        else:
            f = NameObject("/FlateDecode")
        retval = EncodedStreamObject()
        retval[NameObject("/Filter")] = f
        retval._data = FlateDecode.encode(self._data)
        return retval


class DecodedStreamObject(StreamObject):
    def getData(self):
        return self._data

    def setData(self, data):
        self._data = data


class EncodedStreamObject(StreamObject):
    def __init__(self):
        self.decodedSelf = None

    def getData(self):
        if self.decodedSelf:
            # cached version of decoded object
            return self.decodedSelf.getData()
        else:
            # create decoded object
            decoded = DecodedStreamObject()
            decoded._data = decodeStreamData(self)
            for key, value in list(self.items()):
                if not key in ("/Length", "/Filter", "/DecodeParms"):
                    decoded[key] = value
            self.decodedSelf = decoded
            return decoded._data

    def setData(self, data):
        raise PdfReadError("Creating EncodedStreamObject is not currently supported")


class RectangleObject(ArrayObject):
    def __init__(self, arr):
        # must have four points
        assert len(arr) == 4
        # automatically convert arr[x] into NumberObject(arr[x]) if necessary
        ArrayObject.__init__(self, [self.ensureIsNumber(x) for x in arr])

    def ensureIsNumber(self, value):
        if not isinstance(value, (NumberObject, FloatObject)):
            value = FloatObject(value)
        return value

    def __repr__(self):
        return "RectangleObject(%s)" % repr(list(self))

    def getLowerLeft_x(self):
        return self[0]

    def getLowerLeft_y(self):
        return self[1]

    def getUpperRight_x(self):
        return self[2]

    def getUpperRight_y(self):
        return self[3]

    def getUpperLeft_x(self):
        return self.getLowerLeft_x()
    
    def getUpperLeft_y(self):
        return self.getUpperRight_y()

    def getLowerRight_x(self):
        return self.getUpperRight_x()

    def getLowerRight_y(self):
        return self.getLowerLeft_y()

    def getLowerLeft(self):
        return self.getLowerLeft_x(), self.getLowerLeft_y()

    def getLowerRight(self):
        return self.getLowerRight_x(), self.getLowerRight_y()

    def getUpperLeft(self):
        return self.getUpperLeft_x(), self.getUpperLeft_y()

    def getUpperRight(self):
        return self.getUpperRight_x(), self.getUpperRight_y()

    def setLowerLeft(self, value):
        self[0], self[1] = [self.ensureIsNumber(x) for x in value]

    def setLowerRight(self, value):
        self[2], self[1] = [self.ensureIsNumber(x) for x in value]

    def setUpperLeft(self, value):
        self[0], self[3] = [self.ensureIsNumber(x) for x in value]

    def setUpperRight(self, value):
        self[2], self[3] = [self.ensureIsNumber(x) for x in value]

    lowerLeft = property(getLowerLeft, setLowerLeft, None, None)
    lowerRight = property(getLowerRight, setLowerRight, None, None)
    upperLeft = property(getUpperLeft, setUpperLeft, None, None)
    upperRight = property(getUpperRight, setUpperRight, None, None)


def encode_pdfdocencoding(unicode_string):
    retval = bytearray()
    for c in unicode_string:
        try:
            retval.append(_pdfDocEncoding_rev[c])
        except KeyError:
            raise UnicodeEncodeError("pdfdocencoding", c, -1, -1,
                    "does not exist in translation table")
    return bytes(retval)

def decode_pdfdocencoding(byte_array):
    retval = ''
    for b in byte_array:
        c = _pdfDocEncoding[b]
        if c == '\u0000':
            raise UnicodeDecodeError("pdfdocencoding", byte_array, -1, -1,
                    "does not exist in translation table")
        retval += c
    return retval

_pdfDocEncoding = (
  '\u0000', '\u0000', '\u0000', '\u0000', '\u0000', '\u0000', '\u0000', '\u0000',
  '\u0000', '\u0000', '\u0000', '\u0000', '\u0000', '\u0000', '\u0000', '\u0000',
  '\u0000', '\u0000', '\u0000', '\u0000', '\u0000', '\u0000', '\u0000', '\u0000',
  '\u02d8', '\u02c7', '\u02c6', '\u02d9', '\u02dd', '\u02db', '\u02da', '\u02dc',
  '\u0020', '\u0021', '\u0022', '\u0023', '\u0024', '\u0025', '\u0026', '\u0027',
  '\u0028', '\u0029', '\u002a', '\u002b', '\u002c', '\u002d', '\u002e', '\u002f',
  '\u0030', '\u0031', '\u0032', '\u0033', '\u0034', '\u0035', '\u0036', '\u0037',
  '\u0038', '\u0039', '\u003a', '\u003b', '\u003c', '\u003d', '\u003e', '\u003f',
  '\u0040', '\u0041', '\u0042', '\u0043', '\u0044', '\u0045', '\u0046', '\u0047',
  '\u0048', '\u0049', '\u004a', '\u004b', '\u004c', '\u004d', '\u004e', '\u004f',
  '\u0050', '\u0051', '\u0052', '\u0053', '\u0054', '\u0055', '\u0056', '\u0057',
  '\u0058', '\u0059', '\u005a', '\u005b', '\u005c', '\u005d', '\u005e', '\u005f',
  '\u0060', '\u0061', '\u0062', '\u0063', '\u0064', '\u0065', '\u0066', '\u0067',
  '\u0068', '\u0069', '\u006a', '\u006b', '\u006c', '\u006d', '\u006e', '\u006f',
  '\u0070', '\u0071', '\u0072', '\u0073', '\u0074', '\u0075', '\u0076', '\u0077',
  '\u0078', '\u0079', '\u007a', '\u007b', '\u007c', '\u007d', '\u007e', '\u0000',
  '\u2022', '\u2020', '\u2021', '\u2026', '\u2014', '\u2013', '\u0192', '\u2044',
  '\u2039', '\u203a', '\u2212', '\u2030', '\u201e', '\u201c', '\u201d', '\u2018',
  '\u2019', '\u201a', '\u2122', '\ufb01', '\ufb02', '\u0141', '\u0152', '\u0160',
  '\u0178', '\u017d', '\u0131', '\u0142', '\u0153', '\u0161', '\u017e', '\u0000',
  '\u20ac', '\u00a1', '\u00a2', '\u00a3', '\u00a4', '\u00a5', '\u00a6', '\u00a7',
  '\u00a8', '\u00a9', '\u00aa', '\u00ab', '\u00ac', '\u0000', '\u00ae', '\u00af',
  '\u00b0', '\u00b1', '\u00b2', '\u00b3', '\u00b4', '\u00b5', '\u00b6', '\u00b7',
  '\u00b8', '\u00b9', '\u00ba', '\u00bb', '\u00bc', '\u00bd', '\u00be', '\u00bf',
  '\u00c0', '\u00c1', '\u00c2', '\u00c3', '\u00c4', '\u00c5', '\u00c6', '\u00c7',
  '\u00c8', '\u00c9', '\u00ca', '\u00cb', '\u00cc', '\u00cd', '\u00ce', '\u00cf',
  '\u00d0', '\u00d1', '\u00d2', '\u00d3', '\u00d4', '\u00d5', '\u00d6', '\u00d7',
  '\u00d8', '\u00d9', '\u00da', '\u00db', '\u00dc', '\u00dd', '\u00de', '\u00df',
  '\u00e0', '\u00e1', '\u00e2', '\u00e3', '\u00e4', '\u00e5', '\u00e6', '\u00e7',
  '\u00e8', '\u00e9', '\u00ea', '\u00eb', '\u00ec', '\u00ed', '\u00ee', '\u00ef',
  '\u00f0', '\u00f1', '\u00f2', '\u00f3', '\u00f4', '\u00f5', '\u00f6', '\u00f7',
  '\u00f8', '\u00f9', '\u00fa', '\u00fb', '\u00fc', '\u00fd', '\u00fe', '\u00ff'
)

assert len(_pdfDocEncoding) == 256

_pdfDocEncoding_rev = {}
for i in range(256):
    char = _pdfDocEncoding[i]
    if char == "\u0000":
        continue
    assert char not in _pdfDocEncoding_rev
    _pdfDocEncoding_rev[char] = i

