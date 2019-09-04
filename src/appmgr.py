import logging
import threading
import time
import queue
import proxy
import resolver

class AppMgr(threading.Thread):

    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs=None):
        threading.Thread.__init__(self, group=group, target=target, name=name)
        self.name = name
        self.args = args
        self.kwargs = kwargs
        return

    def run(self):
        logging.debug('running with %s and %s',self.args, self.kwargs)

        proxy_req = self.kwargs['a-p']
        proxy_rsp = self.kwargs['p-a']
        resolver_req = self.kwargs['a-r']
        resolver_rsp = self.kwargs['r-a']

        target_hosts = [ "", "www.google.com", "www.yahoo.com", "www.facebook.com","www.instagram.com"]
        #target_ips = [ '', '172.217.6.36', '98.137.246.8', '31.13.70.36', '31.13.70.174']
        target_ips = [ '', '44.1.0.165', '44.1.0.165', '44.1.0.165', '44.1.0.165']
        target_map = {}
        
        for n in [1,2,3,4]:
            logging.debug('issuing new_proxy order: %d',n)
            req_type = "new_proxy"
            hl = '127.0.100.' + str(n)
            args_dict = {'args': (queue.Queue(),queue.Queue()), 
                         'kwargs': {'hostlocal': hl,
                                    'servicelocal': 443,
                                    'hosttarget': target_hosts[n],
                                    'servicetarget': 443,
                                    'edgetarget': '44.1.0.165',
                                    'edgeservice': 443 }}
            target_map[target_hosts[n]] = {'hostlocal': hl,
                                           'servicelocal': 443}
            req = proxy.ProxyMgrReq(id=n, req_type=req_type, args_dict=args_dict)
            proxy_req.put(req)

        logging.debug('new resolver policy: %d',4)
        req_type = "resolver_policy_add"
        args_dict = {'args': (), 
                     'kwargs': {'target_map': target_map}}
        req = resolver.ResolverReq(id=4, req_type=req_type, args_dict=args_dict)
        resolver_req.put(req)


        while True:
            msg  = proxy_rsp.get()
            logging.debug('response: %s',msg)

        logging.debug('exiting')
        return

