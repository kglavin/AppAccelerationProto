
import logging
import threading
import time
import select
import socket
import queue
import message
import serviceheader

###############################################################
class EdgeProcMgrReq(message.Message):
    def __init__(self, id, req_type, args_dict):
        message.Message.__init__(self,id=id)
        self.req_type = req_type
        self.args_dict = args_dict


###############################################################
class EdgeProcMgr(threading.Thread):
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs=None):
        threading.Thread.__init__(self, group=group, target=target, name=name)
        self.name = name
        self.args = args
        self.kwargs = kwargs
        # assume that request and response queues are included as part of the starting of this thread
        self.edgeprocmgr_req = self.kwargs['a-e'] 
        self.edgeprocmgr_rsp = self.kwargs['e-a']
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
            msg  = self.edgeprocmgr_req.get()
            logging.debug('request via %s -  %s',self.edgeprocmgr_req, msg)
            response = self.process_edgeprocmgr_message(msg)
            logging.debug('response via %s -  %s',self.edgeprocmgr_rsp, response)
            self.edgeprocmgr_rsp.put(response)

        logging.debug('exiting')
        return
        
    def process_edgeprocmgr_message(self,msg):
        if msg.req_type == "new_edgeproc":
            # spawn a new proxy thread using the provided kwargs to setup correct proxy behavior.
            args_dict =  msg.args_dict
            edgeproc_args = args_dict['args']
            edgeproc_kwarg = args_dict['kwargs']
            t = EdgeProc(name='edgeproc',
                    args=edgeproc_args, 
                    kwargs=edgeproc_kwarg)
            t.start()
            response = message.Message(id = msg.id, data='ok - edgeproc started')
            logging.debug('exiting with response: %s',response)
            return response
        else:
            # all other commands are not processed at moment. 
            response = message.Message(id = msg.id, data='nok: Unknown request')
            logging.debug('exiting with response: %s',response)
            return response


###############################################################
class EdgeProc(threading.Thread):
    def __init__(self, group=None, target=None, name=None,args=(), kwargs={}):
        threading.Thread.__init__(self, group=group, target=target, name=name)
        self.name = name
        self.args = args
        self.kwargs = kwargs
        self.edgeproc_req, self.edgeproc_rsp = self.args

        if 'hostlocal' in self.kwargs:
            self.hostlocal = self.kwargs['hostlocal']
        else:
            self.hostlocal = '0.0.0.0'
        
        if 'servicelocal' in self.kwargs:
            self.servicelocal = self.kwargs['servicelocal']
        else:
            self.servicelocal = 443

        if 'sharedsecret' in self.kwargs:
            self.sharedsecret = self.kwargs['sharedsecret']
        else:
            self.sharedsecret = b'this is the shared secret'


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

        waiting_for_header = []
        message_qs = {}
        peers = {}

        while inputs:
            for s in inputs:
                if s.fileno() is -1:
                    #logging.debug('dead fd in inputs:%s', str(s))
                    inputs.remove(s)
            for s in outputs:
                if s.fileno() is -1:
                    #logging.debug('dead fd in outputs:%s', str(s))
                    outputs.remove(s)
            if inputs:        
                readable, writable, exceptional = select.select(inputs, outputs, inputs)
                for s in readable:
                    if s is server:
                        connection, client_address = s.accept()
                        connection.setblocking(0)
                        inputs.append(connection)
                        waiting_for_header.append(connection)
                    elif s in waiting_for_header:

                        logging.debug('accepted new connection:%s - %s',client_address, str(connection))

                        #1. read the header from the socket, decode the metadata and derive the target service and port. 
                        sh = serviceheader.ServiceHeader(self.sharedsecret)
                        metadata = None
                        try:
                            # first hundred bytes is the hidden header
                            #logging.debug('headersize: %d',sh.headersize)
                            header = s.recv(sh.headersize)  
                            #logging.debug('header: %s',header)
                            metadata_len = sh.validate_header_magic(header)
                            #logging.debug('metadata len: %d',metadata_len)
                            waiting_for_header.remove(s)
                            if metadata_len > 0:
                                data = s.recv(metadata_len)
                                metadata = sh.extract_metadata(header,data)
                                logging.debug('rx metadata: %s',metadata)
                                if sh.validate_metadata(metadata) is False:  
                                    logging.debug('metadata not valid ')
                                    metadata = None
                        except ConnectionResetError:
                            logging.debug('rx recieve header error connection reset :%d',s.fileno())
                            pass
                        if metadata is None: 
                            logging.debug('no metadata ')
                        else:
                            #logging.debug('rx  metadata :%s', metadata)
                            #2. decode it to decide where we should be connecting to 
                            if 'host' in metadata:
                                target_host = metadata['host']
                            if 'port' in metadata:
                                target_port = metadata['port']

                            # 3. create the connection and associate with with the 
                            st = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            inputs.append(st)

                            #logging.debug('creating new outbound connection:%s:%d and %s',target_host,target_port, str(st))

                            #TODO need a try around this. 
                            st.connect((target_host, target_port))
                            inputs.append(st)
                   
                            logging.debug('created new outbound connection:%s:%d and %s',target_host,target_port, str(st))
                            # entangle the connection and st using the peers list
                            peers[s] = st
                            peers[st] = s
                            message_qs[s] = queue.Queue()
                            message_qs[st] = queue.Queue()
                    else:
                        qsize = 0
                        if s in peers:
                            st = peers[s]
                            if st in message_qs:
                                qsize = message_qs[st].qsize()
                        if qsize > 10:
                              logging.debug('large queue of received data - throttling :%d', qsize)
                        else:  
                            try:
                                if s.fileno() is -1:
                                    logging.debug('dead fd in recv data :%s', str(s))
                                    inputs.remove(s)
                                else:
                                    data = s.recv(4096)  
                            except ConnectionResetError:
                                logging.debug('rx recieve error connection reset :%d',s.fileno())
                                pass
                            if data:
                                #logging.debug('rx receive data - len %d, data: %s',len(data), str(data))
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
                                    #logging.debug('no data, clean up peers :%s ',str(s))
                                    st = peers[s]
                                    #logging.debug('no data, clean up peers - st :%s ',str(st))
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
                                    if s in message_qs:
                                        del message_qs[st]
                                logging.debug('no data, closing sockets :%s ',str(s)) 
                                if s in inputs:  
                                    inputs.remove(s)
                                try:
                                    s.shutdown(1)
                                except OSError:
                                    pass
                                s.close()
                                if s in message_qs:
                                    del message_qs[s]

                for s in writable:
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

    edgeprocmgr_args = ()
    edgeprocmgr_kwargs = {'a-e': req_q,
                          'e-a': rsp_q }
    
    threads = [
        EdgeProcMgr(name='edgeprocmgr',
            args=edgeprocmgr_args, 
            kwargs=edgeprocmgr_kwargs)
        ] 

    for t in threads:
        t.start()
    req_type = "new_edgeproc"
    args_dict = {'args': (queue.Queue(),queue.Queue()), 
                 'kwargs': {'nothing': None}
                 }

    req = EdgeProcMgrReq(id=123, req_type=req_type, args_dict=args_dict)
    req_q.put(req)

