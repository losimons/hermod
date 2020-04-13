"""
This class acts as glue and traffic controller between the various services

The following list shows incoming messages and consquent actions/outgoing messages.
////hotword/detected => dialog/end then wait dialog/ended then dialog/started,
microphone/start, asr/start
////dialog/continue => if text then tts/say then wait tts/finished then  microphone/start,
 asr/start    ELSE microphone/start, asr/start

////dialog/start => if text then dialog/started, asr/stop, nlu/parse ELSE  dialog/started,
 microphone/start, asr/start
////asr/text => asr/stop, hotword/stop, microphone/stop, nlu/parse
////nlu/intent => intent
////nlu/fail => dialog/end
////dialog/end => dialog/ended, microphone/start, hotword/start
////router/action => action
"""

import json
import time
import asyncio
from MqttService import MqttService



class DialogManagerService(MqttService):
    """
    Dialog Manager Service Class
    """
    def __init__(
            self,
            config,
            loop
    ):
        super(
            DialogManagerService,
            self).__init__(config,loop)
        self.log('dm init ')
        self.config = config
        self.subscribe_to = 'hermod/+/hotword/detected,hermod/+/dialog/continue,hermod/+/dialog/start,hermod/+/asr/text,hermod/+/nlu/intent,hermod/+/nlu/fail,hermod/+/dialog/end' 
        self.dialogs = {}
        self.waiters = {}
        self.subscriptions = {}
        self.log('dm init done')
        self.log(self.subscribe_to)
    
    # def on_connect(self, client, userdata, flags, result_code):
        # #self.log("DM Connected with result code {}".format(result_code))
        # # SUBSCRIBE
        # for sub in self.subscribe_to.split(","):
            # self.log('DM subscribe to {}'.format(sub))
            # self.client.subscribe(sub)
        # self.log('dm serv')
        # self.log(self.config['services'])
            
        # # if self.config['services']['DialogManagerService'] and self.config['services']['DialogManagerService']['initialise']:
            # # sites = str(self.config['services']['DialogManagerService']['initialise']).split(",")
            # # for site in sites:
                # # #self.log('initialise site {}'.format(site))
                # # self.client.publish('hermod/'+site+'/hotword/activate')
                # # self.client.publish('hermod/'+site+'/asr/activate')
                # # self.client.publish('hermod/'+site+'/microphone/start')
                # # self.client.publish('hermod/'+site+'/hotword/start')

    # def on_connect(self, client, userdata, flags, result_code):
        # self.log("Connected with result code {}".format(result_code))
        # self.log(self.__class__.__name__)
        # self.log(self.subscribe_to)
        
        # # SUBSCRIBE
        # for sub in self.subscribe_to.split(","):
            # self.log('subscribe to {}'.format(sub))
            # self.client.subscribe(sub)
            
    async def send_and_wait(self, topic, message, waitFor, callback):
        # push callback to waiters and subscribe
        self.waiters[waitFor] = callback
        # keep a tally of subscriptions/topic and limit real subscriptions to
        # one
        sub_count = 0
        if waitFor in self.subscriptions:
            sub_count = self.subscriptions.get(waitFor)
        sub_count = sub_count + 1
        self.subscriptions[waitFor] = sub_count
        # only subscribe for first waiter
        if sub_count < 2:
            await self.client.subscribe(waitFor)
        await self.client.publish(topic, json.dumps(message))

    async def handle_waiters(self, prep, topic, message):
        if topic in self.waiters:
            # remove waiter and decrement (and possibly) unsub subscriptions
            callback = self.waiters.pop(topic, None)
            sub_count = self.subscriptions.get(topic)
            self.subscriptions[topic] = sub_count - 1
            if sub_count == 1:
                # don't unsubscribe dm constant topics
                parts = self.subscribe_to.split(",")
                if topic not in parts:
                    await self.client.unsubscribe(topic)
            await callback(prep, topic, message)

    async def callback_hotword_dialog_ended(self, prep, topic, message):
        await self.client.publish(prep + 'dialog/started', json.dumps({}))
        await self.client.publish(prep + 'asr/start', json.dumps({}))
        await self.client.publish(prep + 'microphone/start', json.dumps({}))
        
    async def callback_dmcontinue_ttsfinished(self, prep, topic, message):
        await self.client.publish(prep + 'asr/start', json.dumps({}))
        await self.client.publish(prep + 'microphone/start', json.dumps({}))
        
    async def start_dialog(self, site, text):
        prep = 'hermod/' + site + '/'
        # if starting with text, dive straight into nlu/parse
        if len(text) > 0:
            await self.client.publish(prep + 'dialog/started', json.dumps({}))
            await self.client.publish(prep + 'asr/stop', json.dumps({}))
            await self.client.publish(prep + 'microphone/stop', json.dumps({}))
            await self.client.publish(prep + 'nlu/parse', json.dumps({"text": text}))
        # otherwise start dialog and asr
        else:
            await self.client.publish(prep + 'dialog/started', json.dumps({}))
            await self.client.publish(prep + 'microphone/start', json.dumps({}))
            await self.client.publish(prep + 'asr/start', json.dumps({}))

    async def on_message(self, msg):
        self.log("DM start message")
        self.log(msg)
        topic = "{}".format(msg.topic)
        parts = topic.split("/")
        site = parts[1]
        #payload_text = "{}".format(msg.payload)
        payload_text = msg.payload
        # self.log("PL text")
        # self.log(payload_text)
        
        payload = {}
        # self.log("DqM MESSAGE {} - {} - {}".format(site,topic,msg.payload))
        try:
            payload = json.loads(payload_text)
        except Exception as e:
            self.log(e)
            pass
        self.log(payload)
        
        prep = 'hermod/' + site + '/'
        # self.log("DaM MESSAGE {} - {} - {}".format(site,topic,prep))

        # first handle temporary subscription bindings
        await self.handle_waiters(prep, topic, payload)
        # now handle main subscription bindings
        if topic == prep + 'hotword/detected':
            # self.log("HW MESSAGE")
            await self.client.publish(prep + 'microphone/stop', json.dumps({}))
            await self.send_and_wait(
                prep + 'dialog/end',
                payload,
                prep + 'dialog/ended',
                self.callback_hotword_dialog_ended)

        elif topic == prep + 'dialog/continue':
            text = payload.get('text','')
            if text:
                await self.send_and_wait(
                    prep + 'tts/say',
                    payload,
                    prep + 'tts/finished',
                    self.callback_dmcontinue_ttsfinished)
            else:
                await self.client.publish(prep + 'asr/start', json.dumps({}))
                await self.client.publish(prep + 'microphone/start', json.dumps({}))
                
        elif topic == prep + 'dialog/start':
            text = payload.get('text','')
            await self.start_dialog(site, text)

        elif topic == prep + 'asr/text':
            text = payload.get('text','')
            await self.client.publish(prep + 'asr/stop', json.dumps({}))
            #self.client.publish(prep + 'hotword/stop', json.dumps({}))
            await self.client.publish(prep + 'microphone/stop', json.dumps({}))
            await self.client.publish(prep + 'nlu/parse', json.dumps({"query": text}))
            
        elif topic == prep + 'nlu/intent':
            await self.client.publish(prep + 'intent', json.dumps(payload))

        elif topic == prep + 'nlu/fail':
            await self.client.publish(prep + 'dialog/end', json.dumps(payload))

        elif topic == prep + 'dialog/end':
            self.log("DM end")
            await self.client.publish(prep + 'dialog/ended', json.dumps({}))
            await self.client.publish(prep + 'asr/stop', json.dumps({}))
            await self.client.publish(prep + 'microphone/start', json.dumps({}))
            await self.client.publish(prep + 'hotword/start', json.dumps({}))

     
