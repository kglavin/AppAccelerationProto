
import os
import sys

loopback = 'lo'
loAddress = "127.0.100."
loNetmask = 'netmask 0xffffff00'
rangeStart = 1
rangeEnd = 254

add_oper = ' add '
del_oper = ' del  '
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
				cmd = "ifconfig " + loopback + ":" + str(n) + " "  + oper + loAddress + str(n) + " netmask 255.0.0.0"
				os.system(cmd)
	if oper == 'show':
		cmd = "ifconfig " + loopback + " " 
		os.system(cmd)


