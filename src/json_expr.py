
import json
import struct

if __name__ == "__main__":

	shared_secret = b'here is a secret'
	id = 1111
	h = hash(shared_secret + str(id).encode())
	a = {  'id': id, 'host': 'www.google.com', 'port': 443, 'user':'kglavin', 'hss': h}
	s = json.dumps(a)
	l = len(s)
	print(s, l)
	magic = 1234
	st = struct.pack('hh',magic,l)
	print(st, len(st))
	rxm, rxl = struct.unpack('hh',st)

	print(rxm,rxl)

	d = json.loads(s)

	rid = d['id']
	host=d['host']
	port = int(d['port'])
	user=d['user']
	hss =d['hss']
	
	rxh = h = hash(shared_secret + str(rid).encode())

	if magic == rxm:
		if hss == rxh:
			print('success: ',rid,host,port,user)
	
