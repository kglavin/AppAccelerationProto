class Message(object):
    """

    """

    def __init__(self, id=0, timestamp=0.0, data=None):
        self.id = id
        self.timestamp = timestamp
        self.data = data
        
    def __str__(self):
        field_strings = ["Id: {0:15.6f}".format(self.id),"Timestamp: {0:15.6f}".format(self.timestamp)]        
        return "    ".join(field_strings).strip()

    def __len__(self):
        return len(self.data)

    def __bool__(self):
        return True

    def __nonzero__(self):
        return self.__bool__()

    #def __repr__(self):
    #    data = ["{:#02x}".format(byte) for byte in self.data]
    #    args = ["timestamp={}".format(self.timestamp),
    #            "data=[{}]".format(", ".join(data))]
    #    return args

    def __eq__(self, other):
        return (isinstance(other, self.__class__) and
                self.data == other.data)

    def __hash__(self):
        return hash((
            self.data
        ))

    def __format__(self, format_spec):
        return self.__str__()