import logging
import threading
import time
import queue
import appmgr
import resolver
import proxy

logging.basicConfig(level=logging.DEBUG,
                    format='[%(asctime)s] (%(threadName)-10s) %(message)s',
                    )

if __name__ == "__main__":

    appmgr_args = ()
    appmgr_kwargs = { 'a-r': queue.Queue(), 
                      'r-a': queue.Queue(),
                      'a-p': queue.Queue(),
                      'p-a': queue.Queue()
                    }

    resolver_args = ()
    resolver_kwargs = {'ip':'127.0.100.253', 
                       'port':53,
                       'a-r': appmgr_kwargs['a-r'],
                       'r-a': appmgr_kwargs['r-a']
                       }

    proxymgr_args = ()
    proxymgr_kwargs = {'a-p': appmgr_kwargs['a-p'],
                      'p-a': appmgr_kwargs['p-a']}      

    threads = [
 
        resolver.Resolver(name='resolver',
                          args=resolver_args, 
                          kwargs=resolver_kwargs),
        proxy.ProxyMgr(name='proxymgr',
            args=proxymgr_args, 
            kwargs=proxymgr_kwargs),
        appmgr.AppMgr(name='appmgr',
            args=appmgr_args, 
            kwargs=appmgr_kwargs),
        ] 
    for t in threads:
        t.start()
        time.sleep(1)



