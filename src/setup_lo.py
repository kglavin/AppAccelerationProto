
import os
import sys

loAddress = "127.0.100."
loNetmask = 'netmask 0xffffff00'
rangeStart = 1
rangeEnd = 254

add_oper = ' alias '
del_oper = ' -alias '
oper = 'show'

if __name__ == "__main__":
	if len(sys.argv) > 1:
		if sys.argv[1] == 'add':
			oper = add_oper
		else:
			if sys.argv[1] == 'del':
				oper = del_oper
		if oper != 'show':
			for n in range(1,254):
				cmd = "ifconfig lo0 " + oper + loAddress + str(n) 
				os.system(cmd)
	if oper == 'show':
		cmd = "ifconfig lo0 " 
		os.system(cmd)


