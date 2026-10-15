"""SDK contracts use in-memory transports or loopback fixtures only."""
import asyncio
import hashlib
import hmac
import json
from pathlib import Path
import socketserver
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, PropertyMock
from urllib.parse import parse_qs

import docker
import requests
import stripe
import telegram
from telegram.request import BaseRequest
from telegram.error import RetryAfter
from press.telegram_utils import Telegram


class TelegramTransport(BaseRequest):
    def __init__(self, fail=False):
        self.calls=[];self.fail=fail;self.closed=False
    @property
    def read_timeout(self): return 3
    async def initialize(self): pass
    async def shutdown(self): self.closed=True
    async def do_request(self, url, method, request_data=None, **kwargs):
        operation=url.rsplit('/',1)[-1]
        self.calls.append((operation, request_data.json_parameters if request_data else {}, kwargs))
        if operation=='getMe':
            value={'id':123456,'is_bot':True,'first_name':'Staging','username':'stage_bot'}
        elif operation=='sendMessage':
            if self.fail:
                return 429,json.dumps({'ok':False,'error_code':429,'description':'Too Many Requests','parameters':{'retry_after':2}}).encode()
            value={'message_id':42,'date':int(time.time()),'chat':{'id':-42,'type':'supergroup'},'text':request_data.json_parameters['text']}
        else:raise AssertionError(operation)
        return 200,json.dumps({'ok':True,'result':value}).encode()


class TelegramContracts(unittest.TestCase):
    def setUp(self):
        self.client=Telegram.__new__(Telegram)
        self.client.token='123456:staging-test-token'
        self.client.chat_id='-42';self.client.topic_id=7
        self.transport=TelegramTransport()
        self.bot=telegram.Bot(token=self.client.token,request=self.transport,get_updates_request=TelegramTransport())
        self.patcher=patch.object(Telegram,'bot',new_callable=PropertyMock,return_value=self.bot)
        self.patcher.start();self.addCleanup(self.patcher.stop)

    def test_send_returns_message_and_preserves_payload(self):
        result=self.client.send('hello',html=True,reraise=True)
        self.assertIsInstance(result,telegram.Message)
        self.assertEqual(result.message_id,42)
        operation,data,timeout=self.transport.calls[-1]
        self.assertEqual(operation,'sendMessage')
        self.assertEqual(data['text'],'hello')
        self.assertEqual(data['chat_id'],'-42')
        self.assertEqual(int(data['message_thread_id']),7)
        self.assertEqual(data['parse_mode'],'HTML')
        for key in ['read_timeout','write_timeout','connect_timeout','pool_timeout']:
            self.assertEqual(timeout[key],3)
        self.assertTrue(self.transport.closed)

    def test_markdown_and_length_limit_preserved(self):
        self.client.send('x'*5000,reraise=True)
        data=self.transport.calls[-1][1]
        self.assertEqual(len(data['text']),4096)
        self.assertEqual(data['parse_mode'],'Markdown')

    def test_empty_message_does_not_contact_transport(self):
        self.assertIsNone(self.client.send(''))
        self.assertEqual(self.transport.calls,[])

    def test_retry_after_propagates_when_requested(self):
        self.transport.fail=True
        with self.assertRaises(RetryAfter):self.client.send('test',reraise=True)
        self.assertTrue(self.transport.closed)

    def test_send_failure_is_logged_when_not_reraised(self):
        self.transport.fail=True
        with patch('press.telegram_utils.log_error') as log:
            self.assertIsNone(self.client.send('test'))
        log.assert_called_once()

    def test_sync_call_from_existing_event_loop(self):
        async def call():return self.client.send('threaded',reraise=True)
        self.assertEqual(asyncio.run(call()).message_id,42)

    def test_respond_ignores_other_groups_before_username_lookup(self):
        self.client.respond({'chat':{'id':-99},'text':'@stage_bot ping'})
        self.assertEqual(self.transport.calls,[])

    def test_respond_keeps_topic_and_only_accepts_own_mention(self):
        message={'chat':{'id':-42},'text':'@stage_bot ping','entities':[{'type':'mention','offset':0,'length':10}],'message_thread_id':8}
        with patch.object(self.client,'process',return_value='pong') as process,patch.object(self.client,'send') as send:
            self.client.respond(message)
        process.assert_called_once_with('ping');send.assert_called_once_with('pong')
        self.assertEqual(self.client.topic_id,8)


class StripeTransport:
    name='staging-contract'
    def __init__(self,status=200):self.calls=[];self.status=status
    def request_with_retries(self,method,url,headers,post_data=None):
        self.calls.append((method,url,headers,post_data))
        if self.status==402:
            data={'error':{'type':'card_error','message':'Synthetic decline','code':'card_declined','param':'card'}}
        else:
            data={'id':'cus_stage' if '/customers' in url else 'seti_stage','object':'customer' if '/customers' in url else 'setup_intent','metadata':{'scope':'local'}}
        return json.dumps(data).encode(),self.status,{}


class StripeContracts(unittest.TestCase):
    def setUp(self):
        self.transport=StripeTransport()
        self.patcher=patch.multiple(stripe,default_http_client=self.transport,api_key='sk_test_staging_contract',api_version=None)
        self.patcher.start();self.addCleanup(self.patcher.stop)

    def test_customer_request_preserves_account_api_version_and_dict_access(self):
        obj=stripe.Customer.create(description='local',metadata={'scope':'local'})
        method,url,headers,body=self.transport.calls[-1]
        self.assertEqual(method,'post');self.assertTrue(url.endswith('/v1/customers'))
        self.assertNotIn('Stripe-Version',headers)
        self.assertEqual(parse_qs(body)['metadata[scope]'],['local'])
        self.assertEqual(obj.get('id'),'cus_stage')
        self.assertEqual(obj['metadata']['scope'],'local')

    def test_setup_intent_and_error_types_preserved(self):
        stripe.SetupIntent.create(customer='cus_stage',usage='off_session')
        self.assertTrue(self.transport.calls[-1][1].endswith('/v1/setup_intents'))
        self.transport.status=402
        with self.assertRaises(stripe.error.CardError):stripe.Customer.create(description='decline')

    def test_requests_transport_and_certificate_validation_on_loopback(self):
        import datetime
        import ipaddress
        import ssl
        import os
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import certifi
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        import OpenSSL

        now=datetime.datetime.now(datetime.timezone.utc)
        ca_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        server_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        ca_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Local SDK test CA')])
        ca=(x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
            .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-datetime.timedelta(minutes=1)).not_valid_after(now+datetime.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False)
            .add_extension(x509.KeyUsage(True,False,False,False,False,True,True,None,None),critical=True)
            .sign(ca_key,hashes.SHA256()))
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
        certificate=(x509.CertificateBuilder().subject_name(name).issuer_name(ca_name)
            .public_key(server_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-datetime.timedelta(minutes=1)).not_valid_after(now+datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
            .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()),critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
            .add_extension(x509.KeyUsage(True,False,True,False,False,False,False,None,None),critical=True)
            .sign(ca_key,hashes.SHA256()))
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                body=b'{"id":"cus_local_tls","object":"customer"}'
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            def log_message(self,*args):pass
        with tempfile.TemporaryDirectory(dir='/tmp',prefix='prs-tls-') as folder:
            folder=Path(folder);keyfile=folder/'key.pem';certfile=folder/'cert.pem';cafile=folder/'ca.pem'
            keyfile.write_bytes(server_key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
            os.chmod(keyfile,0o600)
            certfile.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
            cafile.write_bytes(ca.public_bytes(serialization.Encoding.PEM))
            parsed=OpenSSL.crypto.load_certificate(OpenSSL.crypto.FILETYPE_PEM,certfile.read_bytes())
            self.assertTrue(OpenSSL.crypto.dump_certificate(OpenSSL.crypto.FILETYPE_TEXT,parsed))
            self.assertTrue(OpenSSL.crypto.load_privatekey(OpenSSL.crypto.FILETYPE_PEM,keyfile.read_bytes()))
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(certfile,keyfile)
            with ThreadingHTTPServer(('127.0.0.1',0),Handler) as server:
                server.socket=context.wrap_socket(server.socket,server_side=True)
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                try:
                    with patch.multiple(stripe,api_base=f'https://127.0.0.1:{server.server_port}',ca_bundle_path=str(cafile),default_http_client=None,verify_ssl_certs=True,max_network_retries=0):
                        self.assertEqual(stripe.Customer.create(description='local').id,'cus_local_tls')
                    with patch.multiple(stripe,api_base=f'https://127.0.0.1:{server.server_port}',ca_bundle_path=certifi.where(),default_http_client=None,verify_ssl_certs=True,max_network_retries=0):
                        with self.assertRaises(stripe.error.APIConnectionError):stripe.Customer.create(description='untrusted')
                finally:server.shutdown();thread.join()

    def test_webhook_signature_accepts_valid_and_rejects_invalid(self):
        payload=json.dumps({'id':'evt_stage','object':'event','data':{'object':{'id':'cus_stage'}}})
        timestamp=int(time.time());secret='synthetic-local-webhook-key'
        digest=hmac.new(secret.encode(),f'{timestamp}.{payload}'.encode(),hashlib.sha256).hexdigest()
        header=f't={timestamp},v1={digest}'
        self.assertEqual(stripe.Webhook.construct_event(payload,header,secret)['id'],'evt_stage')
        with self.assertRaises(stripe.error.SignatureVerificationError):stripe.Webhook.construct_event(payload,header,'different-local-key')


class DockerHandler(__import__('http.server',fromlist=['BaseHTTPRequestHandler']).BaseHTTPRequestHandler):
    def do_GET(self):
        if not self.path.endswith('/_ping'):self.send_error(404);return
        self.send_response(200);self.send_header('Content-Length','2');self.end_headers();self.wfile.write(b'OK')
    def log_message(self,*args):pass


class SharedDependencyContracts(unittest.TestCase):
    def test_docker_transport_works_with_framework_requests_on_local_unix_socket(self):
        with tempfile.TemporaryDirectory(dir='/tmp',prefix='prs-dkr-') as folder:
            path=str(Path(folder)/'d.sock')
            with socketserver.UnixStreamServer(path,DockerHandler) as server:
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                try:
                    client=docker.APIClient(base_url='unix://'+path,version='1.45')
                    self.assertTrue(client.ping());client.close()
                finally:server.shutdown();thread.join()

    def test_sql_parser_and_dns_wire_contract(self):
        from sql_metadata import Parser
        import dns.message
        self.assertEqual(Parser('SELECT name FROM tabSite WHERE team = 1').tables,['tabSite'])
        query=dns.message.make_query('stage.invalid','A')
        self.assertEqual(dns.message.from_wire(query.to_wire()).question[0].name.to_text(),'stage.invalid.')

    def test_posthog_legacy_keyword_calls_with_disabled_transport(self):
        from posthog import Posthog
        ph=Posthog('synthetic-local-key',disabled=True)
        ph.capture(distinct_id='local',event='contract',properties={'local':True})
        ph.alias(previous_id='local-old',distinct_id='local-new')
        ph.identify('local',{'local':True})
        ph.shutdown()

    def test_twilio_message_serialization_uses_mock_transport(self):
        from twilio.rest import Client
        from twilio.http.http_client import HttpClient
        from twilio.http.response import Response
        class Transport(HttpClient):
            def __init__(self):
                super().__init__(logger=__import__("logging").getLogger("staging-contract"),is_async=False)
            def request(self,method,uri,**kwargs):
                self.observed=(method,uri,kwargs)
                return Response(201,json.dumps({'sid':'SM'+'0'*32,'body':'local'}))
        transport=Transport();client=Client('AC'+'0'*32,'synthetic-local-secret',http_client=transport)
        result=client.messages.create(to='+15005550006',from_='+15005550006',body='local')
        self.assertEqual(result.sid,'SM'+'0'*32)
        self.assertEqual(transport.observed[2]['data']['Body'],'local')


if __name__=='__main__':unittest.main()
