import logging
import threading
import time
import random
import select
import socket
import queue
import message
import serviceheader


###############################################################
class ProxyMgrReq(message.Message):
    def __init__(self, id, req_type, args_dict):
        message.Message.__init__(self,id=id)
        self.req_type = req_type
        self.args_dict = args_dict

###############################################################
class ProxyMgr(threading.Thread):
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs=None):
        threading.Thread.__init__(self, group=group, target=target, name=name)
        self.name = name
        self.args = args
        self.kwargs = kwargs
        # assume that request and response queues are included as part of the starting of this thread
        self.proxymgr_req = self.kwargs['a-p'] 
        self.proxymgr_rsp = self.kwargs['p-a']
        # currently no intial threads started automatically
        self.initial_threads = []
        # threads that were ordered to be started 
        self.threads = []
        return

    def run(self):
        logging.debug('running with %s and %s',self.args, self.kwargs)
        
        # start initial threads
        for t in self.initial_threads:
            logging.debug('starting initial_thread: %s ',t)
            t.start()

        #loop processing proxymgr_req messages 
        while True:
            msg  = self.proxymgr_req.get()
            logging.debug('request via %s -  %s',self.proxymgr_req, msg)
            response = self.process_proxy_mgr_message(msg)
            logging.debug('response via %s -  %s',self.proxymgr_rsp, response)
            self.proxymgr_rsp.put(response)

        logging.debug('exiting')
        return
        
    def process_proxy_mgr_message(self,msg):

        if msg.req_type == "new_proxy":
            # spawn a new proxy thread using the provided kwargs to setup correct proxy behavior.
            args_dict =  msg.args_dict
            proxy_args = args_dict['args']
            proxy_kwarg = args_dict['kwargs']
            t = Proxy(name='proxy',
                    args=proxy_args, 
                    kwargs=proxy_kwarg)
            t.start()
            response = message.Message(id = msg.id, data='ok')
            logging.debug('exiting with response: %s',response)
            return response
        else:
            # all other commands are not processed at moment. 
            response = message.Message(id = msg.id, data='nok: Unknown request')
            logging.debug('exiting with response: %s',response)
            return response

###############################################################
class Proxy(threading.Thread):
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs={}):
        threading.Thread.__init__(self, group=group, target=target, name=name)
        self.name = name
        self.args = args
        self.kwargs = kwargs
        self.proxy_req, self.proxy_rsp = self.args


        if 'hostlocal' in self.kwargs:
            self.hostlocal = self.kwargs['hostlocal']
        else:
            self.hostlocal = "localhost"
        
        if 'servicelocal' in self.kwargs:
            self.servicelocal = self.kwargs['servicelocal']
        else:
            self.servicelocal = 5443

        if 'hosttarget' in self.kwargs:
            self.hosttarget = self.kwargs['hosttarget']
        else:
            self.hosttarget = "www.google.com"
        
        if 'servicetarget' in self.kwargs:
            self.servicetarget = self.kwargs['servicetarget']
        else:
            self.servicetarget = 443

        if 'sharedsecret' in self.kwargs:
            self.sharedsecret = self.kwargs['sharedsecret']
        else:
            self.sharedsecret = b'this is the shared secret'

        return
    def run(self):
        self.post_run()

    def post_run(self):
        logging.debug('running with %s and %s',self.args, self.kwargs)

        server=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setblocking(0)
        server.bind((self.hostlocal, self.servicelocal))
        server.listen(5)
        logging.debug('server socket bound:%s, %s and %d', str(server), self.hostlocal,self.servicelocal)

        inputs=[server]
        outputs = []
        targets = []
        message_qs = {}
        peers = {}

        while inputs:
            for s in inputs:
                if s.fileno() is -1:
                    logging.debug('dead fd in inputs:%s', str(s))
                    inputs.remove(s)
            for s in outputs:
                if s.fileno() is -1:
                    logging.debug('dead fd in outputs:%s', str(s))
                    outputs.remove(s)
            if inputs:        
                readable, writable, exceptional = select.select(inputs, outputs, inputs)
                for s in readable:
                    # Accept new connections to server
                    if s is server:
                        connection, client_address = s.accept()
                        connection.setblocking(0)
                        inputs.append(connection)
                        
                        # create an outbound socket to the edge processor, create and send the header and metadata prior to 
                        # using the connection as part of the proxy pair. 
                        st = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sh = serviceheader.ServiceHeader(self.sharedsecret)
                        metadata = {} 
                        metadata['host'] = self.hosttarget
                        metadata['port'] = self.servicetarget
                        metadata['id'] = random.randint(1, 200000)
                        header, metadata = sh.generate(metadata)
                        metadata_len = sh.validate_header_magic(header) 

                        logging.debug('creating new outbound connection:%s:%d and %s',self.hosttarget,self.servicetarget, str(st))
                        try:
                            st.connect((self.hosttarget, self.servicetarget))
                            logging.debug('tx  metadata :%s', metadata)
                            st.send(header)
                            st.send(metadata.encode())

                            inputs.append(st)
                            targets.append(st) 
                            logging.debug('created new outbound connection:%s:%d and %s',self.hosttarget,self.servicetarget, str(st))
                            # entangle the connection and st using the peers list
                            peers[connection] = st
                            peers[st] = connection
                            message_qs[connection] = queue.Queue()
                            message_qs[st] = queue.Queue()
                        except ConnectionRefusedError:
                            logging.debug(' edge processor connection refused :%d',s.fileno())
                            st.close()
                            pass
                    else:
                        # process rx from existing sockets, sendind as rx to peer sockets via internal queues 
                        try:
                            data = s.recv(4096)  
                        except ConnectionResetError:
                            logging.debug('rx recieve error connection reset :%d',s.fileno())
                            pass
                        if data:
                            if s in peers:
                                st = peers[s]
                                if st in message_qs:
                                    #logging.debug('queuing rx data on :%d from %d',st.fileno(), s.fileno())
                                    message_qs[st].put(data)
                                if st not in outputs:
                                    outputs.append(st)
                        else:
                            if s in outputs:
                                outputs.remove(s)
                                logging.debug('no data, removing from outputs :%s ',str(s))
                            if s in peers:
                                logging.debug('no data, clean up peers :%s ',str(s))
                                st = peers[s]
                                logging.debug('no data, clean up peers - st :%s ',str(st))
                                del peers[s]
                                del peers[st]
                                if st in inputs:
                                    inputs.remove(st)
                                if st in outputs:
                                    outputs.remove(st)
                                logging.debug('no data, closing sockets st :%s ',str(st)) 
                                try:
                                    st.shutdown(1)
                                except OSError:
                                    pass
                                st.close()
                                del message_qs[st]
                            logging.debug('no data, closing sockets :%s ',str(s))   
                            inputs.remove(s)
                            try:
                                s.shutdown(1)
                            except OSError:
                                pass
                            s.close()
                            if s in message_qs:
                                del message_qs[s]

                for s in writable:
                    # for outbound sockets that are writable, write queued data if there is any
                    try:
                        next_msg = None
                        if s in message_qs:
                            next_msg = message_qs[s].get_nowait()
                        else:
                            ###logging.debug('sending data: no message_qs[%d]', s.fileno())
                            pass
                    except queue.Empty:
                        outputs.remove(s)
                    else:
                        #logging.debug('sending data on :%d', s.fileno())
                        try:
                            if next_msg is not None:
                                s.send(next_msg)
                        except OSError:
                            pass

                for s in exceptional:
                    logging.debug('peer shutdown on :%s ',str(s))
                    if s in peers:
                        st = peers[s]
                        logging.debug('peer shutdown on :%d - %d',s.fileno(), st.fileno())
                        del peers[s]
                        del peers[st]
                        if st in inputs:
                            logging.debug('removing st from inputs :%s ',str(st))
                            inputs.remove(st)
                        if st in outputs:
                            logging.debug('removing st from outputs :%s ',str(st))
                            outputs.remove(st)
                        try:
                            st.shutdown(1)
                        except OSError:
                            pass
                        st.close()
                        del message_qs[st]
                    if s in inputs:
                        logging.debug('removing s from inputs :%s ',str(s))
                        inputs.remove(s)
                    if s in outputs:
                        logging.debug('removing s from outputs :%s ',str(s))
                        outputs.remove(s)
                    try:
                        s.shutdown(1)
                    except OSError:
                        pass
                    s.close()
                    del message_qs[s]

        logging.debug('exiting')
        return

###############################################################
if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG,
                    format='[%(asctime)s] (%(threadName)-10s) %(message)s',
                    )

    req_q = queue.Queue()
    rsp_q = queue.Queue()

    proxymgr_args = ()
    proxymgr_kwargs = {'a-p': req_q,
                       'p-a': rsp_q }
    
    threads = [
        ProxyMgr(name='proxymgr',
            args=proxymgr_args, 
            kwargs=proxymgr_kwargs)
        ] 
    for t in threads:
        t.start()

        target_hosts = [ "www.google.com", "www.yahoo.com", "www.facebook.com","www.instagram.com"]
        for n in [0,1,2,3]:
            logging.debug('issuing new_proxy order: %d',n)
            req_type = "new_proxy"
            args_dict = {'args': (queue.Queue(),queue.Queue()), 
                         'kwargs': {'hostlocal': "localhost",
                                    'servicelocal': 5443+n,
                                    'hosttarget': target_hosts[n],
                                    'servicetarget': 443 }}
            req = ProxyMgrReq(id=n, req_type=req_type, args_dict=args_dict)
            req_q.put(req)

        t.join()
    logging.debug('exiting')

