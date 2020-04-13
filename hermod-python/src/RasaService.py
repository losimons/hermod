from MqttService import MqttService
import sys
import time
import json
import requests
import aiohttp
import asyncio
import async_timeout


class RasaService(MqttService):

    def __init__(
            self,
            config,
            loop
    ):
        super(
            RasaService,
            self).__init__(config,loop)
        self.config = config
        # self.recursion_depth = {}
        self.rasa_server = self.config['services']['RasaService'].get('rasa_server','http://localhost:5005/')
        self.subscribe_to = 'hermod/+/dialog/ended,hermod/+/nlu/parse,hermod/+/intent,hermod/+/intent,hermod/+/dialog/started'
        
        
    async def connect_hook(self):
        # self.log("Connected with result code {}".format(result_code))
        # SUBSCRIBE
        for sub in self.subscribe_to.split(","):
            self.log('RASA subscribe to {}'.format(sub))
            await self.client.subscribe(sub)
        
        while True:
            self.log('check rasa service '+self.rasa_server)
            try:
                self.log('rasa service GET '+self.rasa_server)
                response = requests.get(self.rasa_server)
                self.log('rasa service GOT '+self.rasa_server)
                if response.status_code == 200:
                    self.log('FOUND rasa service')
                    break
                time.sleep(3)
            except Exception as e: 
                self.log(e)
                pass
            time.sleep(3)
        #time.sleep(2)
        await self.client.publish('hermod/rasa/ready',json.dumps({}))
                   
    async def on_message(self, msg):
        topic = "{}".format(msg.topic)
        parts = topic.split("/")
        site = parts[1]
        self.log("RASA MESSAGE {}".format(topic))
        ps = str(msg.payload, encoding='utf-8')
        payload = {}
        text = ''
        try:
            payload = json.loads(ps)
        except BaseException:
            pass
        self.log(payload)
        if topic == 'hermod/' + site + '/nlu/parse':
            if payload: 
                text = payload.get('query')
                await self.nlu_parse_request(site,text)
        
        elif topic == 'hermod/' + site + '/intent':
            if payload:
                # self.log('HANDLE INTENT')
                await self.handle_intent(topic,site,payload)

        elif topic == 'hermod/' + site + '/tts/finished':
            await self.client.unsubscribe('hermod/'+site+'/tts/finished')
            await self.finish(site)
            
        elif topic == 'hermod/' + site + '/dialog/ended':
            await self.reset_tracker(site) 
   
    
    async def reset_tracker(self,site):
        self.log('reset tracker '+site)
        #requests.post(self.rasa_server+"conversations/"+site+"/tracker/events",json.dumps({"event": "restart"}))
        #requests.put(self.rasa_server+"/conversations/"+site+"/tracker/events",json.dumps([]),headers = {'content-type': 'application/json'})
        await self.request_put(self.rasa_server+"/conversations/"+site+"/tracker/events",[])

    async def handle_intent(self,topic,site,payload):
        await self.client.publish('hermod/'+site+'/core/started',json.dumps({}));
        self.log('SEND RASA TRIGGER {}  {} '.format(self.rasa_server+"/conversations/"+site+"/trigger_intent",json.dumps({"name": payload.get('intent').get('name'),"entities": payload.get('entities')})))
        #response = requests.post(self.rasa_server+"/conversations/"+site+"/trigger_intent",json.dumps({"name": payload.get('intent').get('name'),"entities": payload.get('entities')}),headers = {'content-type': 'application/json'})
        response =await self.request_post(self.rasa_server+"/conversations/"+site+"/trigger_intent",{"name": payload.get('intent').get('name'),"entities": payload.get('entities')})
        self.log('resp RASA TRIGGER')
        messages = response.get('messages')
        self.log('HANDLE INTENT MESSAGES')
        self.log(messages)
        if messages:
            self.log('SEND MESSAGES')
            message = '. '.join(map(lambda x: x.get('text',''   ),messages))
            self.log(message)
            await self.client.subscribe('hermod/'+site+'/tts/finished')
            self.log('SEND MESSAGES sub finish')
            await self.client.publish('hermod/'+site+'/tts/say',json.dumps({"text":message}))
            self.log('SEND MESSAGES sent text')
            # send action messages from server actions to client action
            # for message in messages:
                # self.log(message)
                # # if hasattr(message,'action') and message.action:
                    # # await self.client.publish('hermod/'+site+'/action',json.dumps(message.action))
        else:
            self.log('SEND finish')
            await self.finish(site)
        
    async def finish(self,site):
        #self.log('finish')
        #response = requests.get(self.rasa_server+"/conversations/"+site+"/tracker",json.dumps({}))
        response = await self.request_get(self.rasa_server+"/conversations/"+site+"/tracker",{})
        self.log(response)
        events = response.get('events',[])
        # end conversation
        if len(events) > 0 and events[len(events) - 2].get('event') == 'action'  and events[len(events) - 2].get('name') == 'action_end':
            # restart hotword
            await self.client.publish('hermod/'+site+'/dialog/end',json.dumps({}));
        else:
            # restart asr
            await self.client.publish('hermod/'+site+'/dialog/continue',json.dumps({}));
    
# event_loop = asyncio.get_event_loop()
# Then later, inside your Thread:

# asyncio.ensure_future(my_coro(), loop=event_loop)

    async def nlu_parse_request(self,site,text):
        self.log('PARSE REQUEST')
        self.log(text)
        self.log(self.rasa_server+"/model/parse")
        self.log(json.dumps({"text":text,"message_id":site})    )
        response = await self.request_post(self.rasa_server+"/model/parse",{"text":text,"message_id":site})
        #response = requests.post(self.rasa_server+"/model/parse",data = json.dumps({"text":text,"message_id":site}),headers = {'content-type': 'application/json'})
        self.log('PARSE RESPONSE')
        self.log(response)
        await self.client.publish('hermod/'+site+'/nlu/intent',json.dumps(response))

    async def request_get(self,url,json):
        with async_timeout.timeout(10):
            async with aiohttp.ClientSession() as session:
                async with session.get(url,json = json, headers = {'content-type': 'application/json'}) as resp:
                    print(resp.status)
                    return await resp.json()

    async def request_post(self,url,json):
        with async_timeout.timeout(10):
            async with aiohttp.ClientSession() as session:
                async with session.post(url,json=json,headers = {'content-type': 'application/json'}) as resp:
                    print(resp.status)
                    return await resp.json()
            
    async def request_put(self,url,json):
        with async_timeout.timeout(10):
            async with aiohttp.ClientSession() as session:
                async with session.put(url,json=json,headers = {'content-type': 'application/json'}) as resp:
                    print(resp.status)
                    return await resp.json()
            
            
            # async with session.get(url) as response:
                # return await response.text()

    # async def main():
        # async with aiohttp.ClientSession() as session:
            # html = await self.fetch(session, 'http://python.org')
            # print(html)
