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
Implementation of stream filters for PDF.
"""
__author__ = "Mathieu Fenniak"
__author_email__ = "mfenniak@pobox.com"

import zlib
from generic import NameObject

class FlateDecode(object):
    def decode(data, decodeParms):
        data = zlib.decompress(data)
        predictor = 1
        if decodeParms:
            predictor = decodeParms.get("/Predictor", 1)
        # predictor 1 == no predictor
        if predictor != 1:
            columns = decodeParms["/Columns"]
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
    decode = staticmethod(decode)

class ASCIIHexDecode(object):
    def decode(data, decodeParms=None):
        retval = ""
        char = ""
        x = 0
        while True:
            c = data[x]
            if c == ">":
                break
            elif c.isspace():
                x += 1
                continue
            char += c
            if len(char) == 2:
                retval += chr(int(char, base=16))
                char = ""
            x += 1
        assert char == ""
        return retval
    decode = staticmethod(decode)

def decodeStreamData(stream):
    filters = stream.get("/Filter", ())
    if len(filters) and not isinstance(filters[0], NameObject):
        # we have a single filter instance
        filters = (filters,)
    data = stream['__streamdata__']
    for filterType in filters:
        if filterType == "/FlateDecode":
            data = FlateDecode.decode(data, stream.get("/DecodeParms"))
        elif filterType == "/ASCIIHexDecode":
            data = ASCIIHexDecode.decode(data)
        else:
            # unsupported filter
            assert False
    return data

if __name__ == "__main__":
    assert "abc" == ASCIIHexDecode.decode('61\n626\n3>')
