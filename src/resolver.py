import logging
import socket
import threading
import queue
import select
import time
import dns.message
import dns.query
import procinspect
import message
import dns.rrset
import dns.rdatatype
import dns.rdataclass


###############################################################
class ResolverReq(message.Message):
    def __init__(self, id, req_type, args_dict):
        message.Message.__init__(self,id=id)
        self.req_type = req_type
        self.args_dict = args_dict

#########################################
class TxResolver(threading.Thread):
    def __init__(self, group=None, target=None, name=None,
                 args=(-1,None), kwargs=None, verbose=None):
        threading.Thread.__init__(self, group=group, target=target, name=name)
        self.name = name
        self.args = args
        self.kwargs = kwargs
        # unwrap the positional args
        self.s,self.tx_queue = self.args
        return

    def run(self):
        logging.debug('running with %s and %s',self.args, self.kwargs)

        # loop of taking items from tx_queue
        # check are they dns messages
        # send via socket to upstream resolver
        while True:
            qitem = self.tx_queue.get()
            addr,m = qitem
            ###logging.debug("tx: %s, %s",addr,m.id)
            dns.query.send_udp(self.s,m,addr)

        logging.debug('exiting')
        return
#########################################
class RxResolver(threading.Thread):
    def __init__(self, group=None, target=None, name=None,
                 args=(-1,None), kwargs=None, verbose=None):
        threading.Thread.__init__(self, group=group, target=target, name=name)
        self.name = name
        self.args = args
        self.kwargs = kwargs
        # unwrap the positional args
        self.s,self.rx_queue = self.args
        return

    def run(self):
        logging.debug('running with %s and %s',self.args, self.kwargs)

        # loop of taking receiving data from socket  
        # and placing them onto rx_queue

        while True:
            data,addr = self.s.recvfrom(512)
            m = dns.message.from_wire(data)
            ###logging.debug("rx: %s, %s",addr,m.id)
            qitem = (addr,m)
            self.rx_queue.put(qitem)

        logging.debug('exiting')
        return

#########################################
class Resolver(threading.Thread):
    def __init__(self, group=None, target=None, name=None,
                 args=(), kwargs=None, verbose=None):
        threading.Thread.__init__(self, group=group, target=target, name=name)
        self.name = name
        self.args = args
        self.kwargs = kwargs
        
        # Queues from AppMgr to all it configure dns policy changes. 
        self.resolver_req = self.kwargs['a-r'] 
        self.resolver_rsp = self.kwargs['r-a']

        # internal Queues for client (to upstream dns server) 
        self.client_tx_queue = queue.Queue()
        self.client_rx_queue = queue.Queue()

        # internal Queues for server (from device) 
        self.server_tx_queue = queue.Queue()
        self.server_rx_queue = queue.Queue()

        # internal Queues for proc_inspect 
        self.proc_inspect_req = queue.Queue()
        self.proc_inspect_rsp = queue.Queue()


        if 'ip' in self.kwargs:
            self.ip = self.kwargs['ip']
        else:
            self.ip = "127.0.0.1"

        if 'port' in self.kwargs:
            self.port = self.kwargs['port']
        else:
            self.port = 15353

        self.target_map = {}

        return

    def run(self):
        logging.debug('running with %s and %s',self.args, self.kwargs)

        # server socket is bound to an internal (127) address to provide resolution inside the node
        s_server = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        s_server.bind((self.ip,self.port))
        logging.debug('server socket bound:%s, %s and %d',s_server,self.ip, self.port)

        #client socket is bound to the standard address so that it can be used to make upstream requests
        s_client = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        s_client.bind(('', 0))
        logging.debug('client socket bound:%s,  %s',s_client, str(s_client.getsockname()))

        # c_*_resolver interacts upstream
        # s_*_resolver interacts with local processes serving them dns requests
        threads = [
            procinspect.ProcInspect(name='proc_inspect',
                      args=(self.proc_inspect_req,self.proc_inspect_rsp), 
                      kwargs={}),
            TxResolver(name='c_tx_resolver',
                      args=(s_client,self.client_tx_queue), 
                      kwargs={}),
            RxResolver(name='c_rx_resolver',
                          args=(s_client,self.client_rx_queue), 
                          kwargs={}),
            TxResolver(name='s_tx_resolver',
                      args=(s_server,self.server_tx_queue), 
                      kwargs={}),
            RxResolver(name='s_rx_resolver',
                          args=(s_server,self.server_rx_queue), 
                          kwargs={}),
            ] 

        for t in threads:
            logging.debug('starting thread: %s', t.name)
            t.start()

        
        #local vars used in select processing and maintaining state of dns queries.
        request_state = {}
        #inputs = [s_server, s_client]
        inputs = []
        outputs = []
        timeout=0.2


        # select on sockets with timeout, assuming that the recv will fire before the select, 
        # may need to change to some other type of inter thread signalling as this select may only work on timeout
        while True:
            readable, writable, exceptional = select.select(inputs, outputs, inputs,timeout)
            for s in readable:
                logging.debug('select readable: %s', s)
            for s in exceptional:
                logging.debug('select exceptional: %s', s)
            if not (readable or writable or exceptional):
                #logging.debug('select timeout:')
                pass
     
            # with viable data on a socket or a timeout attempt to check for the various 
            # async conditions 
            
            # # 
            # # RESPONSE PROCESSING
            # # 
            # [>> 1] check for any proc_inspect_responses
            #
            #  if there is a proc inspect response -- 
            #  State Transition
            #  Wait_for_first_response -> Wait_for_response_A
            #  OR
            #  Wait_for_response_B -> Idle

            try:
                qitem = self.proc_inspect_rsp.get_nowait()
            except queue.Empty:
                pass
            else:
                lport,mid,pi_rsp = qitem
                ###logging.debug('client_rxqueue: lport %d, m.id %d, proc_ident_rsp ,%s', lport,mid,pi_rsp)
                
                #find the address of the original requesting process from the stored state
                if mid in request_state:
                    client_addr,t_id,t_question,lp,dns_rsp, _ = request_state[m.id]
                    if lp != lport:
                        logging.debug('client_rxqueue: lport %d not found in request_state, m.id %d',lport,mid)
                    else:
                        if dns_rsp is not None:
                            #1 send the dns response to client ( TODO this needs to be modified to use localhost address based on procinfo)
                            ###logging.debug('client_rxqueue: sending to server_tx %s, %d,proc_info %s',client_addr, m.id,m)
                            server_qitem = (client_addr,m)
                            self.server_tx_queue.put(server_qitem)
                            del request_state[m.id]
                        else:
                             # store pi_rsp and wait for dns_rsp to arrive   
                             request_state[mid] = (client_addr,t_id,t_question,lport,dns_rsp, pi_rsp)
                else:
                    logging.debug('client_rxqueue: m.id not found, message dumped - %d',m.id)


            # # [>> 2]  is there a dns response from upstream, find the address of the local process 
            # that requested and process it downstream
            # check client_rx_queue and sent to server_tx_queue
            #
            #  if there is a proc inspect response -- 
            #  State Transition
            #  Wait_for_first_response -> Wait_for_response_B
            #  OR 
            #  Wait_for_response_A -> Idle
            try:
                qitem = self.client_rx_queue.get_nowait()
            except queue.Empty:
                pass
            else:
                addr,m = qitem
                ###logging.debug('client_rxqueue: addr %s, m.id ,%d, m.quest, %s, m.ans, %s', addr, m.id, m.question, m.answer)
                
                #find the address of the original requesting process from the stored state
                if m.id in request_state:
                    client_addr,t_id,t_question,lport, _, pi_rsp = request_state[m.id]
                    dns_rsp = m

                    #
                    # POLICY CHANGE
                    # if the requested name resultion is in the target_map insert this as the answer instead of 
                    # using the upstream answer. 
                    # TODO: assuming its an A record we are looking for 
                    q = m.question[0].name
                    dns_q_name = str(q).rstrip('.')
                    ###logging.debug(' dns_q_name: %s, %s', dns_q_name, q)
                    if dns_q_name in self.target_map:
                        target_result = self.target_map[dns_q_name]['hostlocal']
                        dns_result = dns.rrset.from_text(dns_q_name+'.', 300, 'in', 'a', target_result)
                        logging.debug(' dns_result: %s', dns_result)
                        dns_rsp.answer = [dns_result]


                    #if have both responses act, otherwise wait for second response
                    if pi_rsp is not None:
                        #1 send the dns response to client ( TODO this needs to be modified to use localhost address based on procinfo)
                        ###logging.debug('client_rxqueue: sending to server_tx %s, %d,proc_info %s',client_addr, m.id,m)
                        server_qitem = (client_addr,m)
                        self.server_tx_queue.put(server_qitem)
                        del request_state[m.id]
                    else:
                        # copy the dns response into state and wait for proc_info response
                        request_state[m.id] = (client_addr,t_id,t_question,lport,dns_rsp, pi_rsp)
                else:
                    logging.debug('client_rxqueue: m.id not found, message dumped - %d',m.id)

            # # 
            # # REQUEST PROCESSING
            # # 
            # # [>> 3]  is there a dns query from a local process, process it upstream
            # check server_rx_queue and sent to client_tx_queue
            # 
            # State Transition Idle->Wait_for_first_response

            # -- this is the initial state transition, a client process has requested a dns resolution, 
            #    initiate a request to get process info details, 
            #    initiate an upstead DNS request based on the received info. 
            #    transition to waiting for responses for either of these two requests. 
            try:
                qitem = self.server_rx_queue.get_nowait()
            except queue.Empty:
                pass
            else:
                addr,m = qitem
                lip,lport = addr
                ###logging.debug('server_rxqueue: addr %s, m.id %d, m.quest %s, m.ans, %s', addr, m.id, m.question, m.answer)

                # issue a proc identification request based on localport
                self.proc_inspect_req.put((lport,m.id))

                # maintain a mapping of dns query id to requesting address so when response comes back 
                # the response can be sent downstream to the proper process
                if m.id in request_state:
                    logging.debug('server_rxqueue: already in request state should not be rx ,%s', m.id)
                request_state[m.id] = (addr, m.id, m.question,lport,None,None) # (first NONE is for DNS resposne, Second for Proc Response) 

                # issue a generic dns request (TODO this is hardcoded and needs to change)
                dns_res_addr = ('44.1.13.1',53)
                client_qitem = (dns_res_addr,m)
        
                ###logging.debug('server_rxqueue: sending to client_tx %s, %d',dns_res_addr, m.id)
                self.client_tx_queue.put(client_qitem)
                


            #  [>> 4 ] is there a ????
            #  
            try:
                msg = self.resolver_req.get_nowait()
            except queue.Empty:
                pass
            else:
                logging.debug('resolver request received: %s', msg)
                if msg.req_type == "resolver_policy_add": 
                    logging.debug('resolver policy add:')
                    args_dict =  msg.args_dict
                    resolver_args = args_dict['args']
                    resolver_kwarg = args_dict['kwargs']
                    self.target_map = resolver_kwarg['target_map']
                    logging.debug('target_map: %s', self.target_map)
                    response = message.Message(id = msg.id, data='ok')
                    self.resolver_rsp.put(response)
                else:
                    response = message.Message(id = msg.id, data='nok:   message type not processed')
                    self.resolver_rsp.put(response)


        #cleanup threads 
        for t in threads:
            logging.debug('joining thread', t.name)
            t.join()
        time.sleep(2)
        logging.debug('exiting')
        return
