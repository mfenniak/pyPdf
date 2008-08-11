import re
import datetime
import decimal
from generic import PdfObject
from xml.dom import getDOMImplementation
from xml.dom.minidom import parseString

RDF_NAMESPACE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"
XMP_NAMESPACE = "http://ns.adobe.com/xap/1.0/"

iso8601 = re.compile("""
        (?P<year>[0-9]{4})
        (-
            (?P<month>[0-9]{2})
            (-
                (?P<day>[0-9]+)
                (T
                    (?P<hour>[0-9]{2}):
                    (?P<minute>[0-9]{2})
                    (:(?P<second>[0-9]{2}(.[0-9]+)?))?
                    (?P<tzd>Z|[-+][0-9]{2}:[0-9]{2})
                )?
            )?
        )?
        """, re.VERBOSE)

class XmpInformation(PdfObject):

    def __init__(self, stream):
        self.stream = stream
        docRoot = parseString(self.stream.getData())
        self.rdfRoot = docRoot.getElementsByTagNameNS(RDF_NAMESPACE, "RDF")[0]
        self.cache = {}

    def writeToStream(self, stream, encryption_key):
        self.stream.writeToStream(stream, encryption_key)

    def getElement(self, aboutUri, namespace, name):
        for desc in self.rdfRoot.getElementsByTagNameNS(RDF_NAMESPACE, "Description"):
            if desc.getAttributeNS(RDF_NAMESPACE, "about") == aboutUri:
                attr = desc.getAttributeNodeNS(namespace, name)
                if attr != None:
                    yield attr
                for element in desc.getElementsByTagNameNS(namespace, name):
                    yield element

    def _getText(self, element):
        text = ""
        for child in element.childNodes:
            if child.nodeType == child.TEXT_NODE:
                text += child.data
        return text

    def _converter_string(value):
        return value

    def _converter_date(value):
        m = iso8601.match(value)
        year = int(m.group("year"))
        month = int(m.group("month") or "1")
        day = int(m.group("day") or "1")
        hour = int(m.group("hour") or "0")
        minute = int(m.group("minute") or "0")
        second = decimal.Decimal(m.group("second") or "0")
        seconds = second.to_integral(decimal.ROUND_FLOOR)
        milliseconds = (second - seconds) * 1000000
        tzd = m.group("tzd") or "Z"
        dt = datetime.datetime(year, month, day, hour, minute, seconds, milliseconds)
        if tzd != "Z":
            tzd_hours, tzd_minutes = [int(x) for x in tzd.split(":")]
            tzd_hours *= -1
            if tzd_hours < 0:
                tzd_minutes *= -1
            dt = dt + datetime.timedelta(hours=tzd_hours, minutes=tzd_minutes)
        return dt
    _test_converter_date = staticmethod(_converter_date)

    def _getter_bag(namespace, name, converter):
        def get(self):
            cached = self.cache.get(namespace, {}).get(name)
            if cached:
                return cached
            retval = []
            for element in self.getElement("", namespace, name):
                bag = element.getElementsByTagNameNS(RDF_NAMESPACE, "Bag")[0]
                for item in bag.getElementsByTagNameNS(RDF_NAMESPACE, "li"):
                    value = self._getText(item)
                    value = converter(value)
                    retval.append(value)
            ns_cache = self.cache.setdefault(namespace, {})
            ns_cache[name] = retval
            return retval
        return get

    def _getter_seq(namespace, name, converter):
        def get(self):
            cached = self.cache.get(namespace, {}).get(name)
            if cached:
                return cached
            retval = []
            for element in self.getElement("", namespace, name):
                bag = element.getElementsByTagNameNS(RDF_NAMESPACE, "Seq")[0]
                for item in bag.getElementsByTagNameNS(RDF_NAMESPACE, "li"):
                    value = self._getText(item)
                    value = converter(value)
                    retval.append(value)
            ns_cache = self.cache.setdefault(namespace, {})
            ns_cache[name] = retval
            return retval
        return get

    def _getter_single(namespace, name, converter):
        def get(self):
            cached = self.cache.get(namespace, {}).get(name)
            if cached:
                return cached
            for element in self.getElement("", namespace, name):
                if element.nodeType == element.ATTRIBUTE_NODE:
                    value = element.nodeValue
                else:
                    value = self._getText(element)
                break
            value = converter(value)
            ns_cache = self.cache.setdefault(namespace, {})
            ns_cache[name] = value
            return value
        return get

    dc_contributor = property(_getter_bag(DC_NAMESPACE, "contributor", _converter_string))
    dc_coverage = property(_getter_single(DC_NAMESPACE, "coverage", _converter_string))
    dc_creator = property(_getter_seq(DC_NAMESPACE, "creator", _converter_string))
    dc_date = property(_getter_seq(DC_NAMESPACE, "date", _converter_date))

    def get_xmpCreateDate(self):
        element = self.getElement("", XMP_NAMESPACE, "CreateDate")
        print repr(element)

