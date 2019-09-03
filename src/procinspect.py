import logging
import threading
import time
import psutil

def find_proc_info(port):
    conns = psutil.net_connections(kind='inet')
    #sconn(fd=20, family=<AddressFamily.AF_INET: 2>, type=2, laddr=addr(ip='0.0.0.0', port=61905), raddr=(), status='NONE', pid=59605)
    # based on this format the local address port is conns[0][3][1]
    #type(a[3][1]) == <int>
    for a in conns:
        if a[3][1] == port:
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
            return(pid,pname,pcreate,ppid,pstatus,pexe,uids,username)
    return(None,None,None,None,None,None,None,None)

class ProcInspect(threading.Thread):

    def __init__(self, group=None, target=None, name=None,
                 args=(None, None), kwargs=None):
        threading.Thread.__init__(self, group=group, target=target, name=name)
        self.name = name
        self.args = args
        self.kwargs = kwargs
        # unwrap the positional args
        self.request_q,self.response_q = self.args
        return

    def run(self):
        logging.debug('running with %s and %s',self.args, self.kwargs)
        if self.request_q is None or self.response_q is None:
            logging.debug('exiting: request or resonse queue is None')
            return
        
        while True:
            (pitem,mid) = self.request_q.get()
            ###logging.debug('request: port %d,mid %d',pitem,mid)
            response = find_proc_info(pitem)
            logging.debug('response: pitem %d, mid %d, rsp %s',pitem,mid,response)
            self.response_q.put((pitem,mid,response))

        logging.debug('exiting')
        return

