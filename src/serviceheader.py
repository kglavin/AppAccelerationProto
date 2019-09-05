
import logging
import json
import struct
import hashlib

class ServiceHeader(object):
    
    def __init__(self,sharedsecret=None):
        self.magic = 1279
        self.sharedsecret = sharedsecret
        # based on size of 4 shorts in struct.pack('hhhh',self.magic, l,l,self.magic)
        self.headersize = 8 

    def generate(self,metadata,id=None,):
        if metadata is None:
            return(0,None)
        if 'id' not in metadata: 
            metadata['id'] = id
        if metadata['id'] is not None:
            m = hashlib.md5()
            m.update(self.sharedsecret  + str(metadata['id']).encode() + str(metadata['host']).encode() + str(metadata['port']).encode())
            metadata['md5'] = m.hexdigest()
        else:
            return(0,None)
        md_json = json.dumps(metadata)
        l = len(md_json)
        header = struct.pack('hhhh',self.magic, l,l,self.magic)
        return (header,md_json)

    def validate_header_magic(self, header=None):
        length = 0
        if header is not None:
            magic, length, l2, m2 = struct.unpack('hhhh',header)
            if magic != self.magic or m2 != self.magic:
                length = 0
        return length

    def validate_metadata(self, metadata=None):
        if metadata is None:
            return False
        if 'id' in metadata and 'md5' in metadata:
            m = hashlib.md5()
            m.update(self.sharedsecret + str(metadata['id']).encode() + str(metadata['host']).encode() + str(metadata['port']).encode())
            calculated_h = m.hexdigest()
            if metadata['md5'] == calculated_h:
                return True
            else:
                logging.debug('metadata[md5] != calculated md5: %s', metadata)

        return False

    def extract_metadata(self, header=None, buf=None):
        d = None
        if header is not None and buf is not None:
            magic, length,l2,m2 = struct.unpack('hhhh',header)
            if magic != self.magic or self.magic !=m2:
                d = None
            else:
                if length == len(buf):
                    d = json.loads(buf)
        return d

if __name__ == "__main__":

    sh = ServiceHeader(b'this is the shared secret')
    metadata = {'host': 'www.google.com', 'port': 443, 'user':'kglavin'}
    print('original metadata:', metadata)
    header,md_json = sh.generate(metadata,4445)
    gen_len = sh.validate_header_magic(header)
    print('len of header:', len(header))
    print('generated_len of metadata: ',gen_len)
    if sh.validate_metadata(metadata) is True:
        print('metadata is valid')
    else:
        print('metadata is invalid')
    rx_d = sh.extract_metadata(header,md_json)
    print('received metadata:',rx_d)
    






