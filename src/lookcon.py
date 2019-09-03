import psutil

conns = psutil.net_connections(kind='inet')
for a in conns:
    #sconn(fd=20, family=<AddressFamily.AF_INET: 2>, type=2, laddr=addr(ip='0.0.0.0', port=61905), raddr=(), status='NONE', pid=59605)
    # based on this format the local address port is conns[0][3][1]
    #type(a[3][1]) == <int>
    if a[3][1] == 49314:
        print(a)
        print("port == ",a[3][1])
        print("pid == ",a[6])
        pid = a[6]
        p  = psutil.Process(pid)
        with p.oneshot():
            pname=p.name()  # execute internal routine once collecting multiple info
            pcreate=p.create_time()  # return cached value
            ppid = p.ppid()  # return cached value
            pstatus = p.status()  # return cached value
            pexe = p.exe()
            uids = p.uids()
            username = p.username()
        print(pid,":",pname,":",pcreate,":",ppid,":",pstatus,":",pexe,":",uids,":",username)

