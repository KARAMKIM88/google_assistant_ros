#!/usr/bin/env python
# -*- coding: utf-8 -*-
# reference : https://github.com/googlesamples/assistant-sdk-python/blob/master/google-assistant-sdk/googlesamples/assistant/grpc/pushtotalk.py



import rospy
from std_msgs.msg import String
from geometry_msgs.msg import Twist

import json
import logging

import uuid
import sys
reload(sys)
sys.setdefaultencoding('utf-8')


import time
import os
import os.path
import pathlib2 as pathlib

import click
import grpc
import google.auth.transport.grpc
import google.auth.transport.requests
import google.oauth2.credentials
import os # need to sudo apt-get install sox



from google.assistant.embedded.v1alpha2 import(
    embedded_assistant_pb2,
    embedded_assistant_pb2_grpc
)
from tenacity import retry, stop_after_attempt, retry_if_exception



package_dir = os.path.dirname(os.path.abspath(__file__))
print(package_dir)

try:
    from package_dir import (
        assistant_helpers,
        audio_helpers,
        browser_helpers,
        device_helpers
    )
except (SystemError, ImportError):
    import assistant_helpers
    import audio_helpers
    import browser_helpers
    import device_helpers


"""
def talker():
    pub = rospy.Publisher("chatter", String, queue_size=5)
    rospy.init_node('talker', anonymous=True)
    rate = rospy.Rate(10)
    while not rospy.is_shutdown():
        hello_str = "hello world %s" % rospy.get_time()
        rospy.loginfo(hello_str)
        pub.publish(hello_str)
        rate.sleep()
"""


ASSISTANT_API_ENDPOINT = 'embeddedassistant.googleapis.com'
END_OF_UTTERANCE = embedded_assistant_pb2.AssistResponse.END_OF_UTTERANCE
DIALOG_FOLLOW_ON = embedded_assistant_pb2.DialogStateOut.DIALOG_FOLLOW_ON
CLOSE_MICROPHONE = embedded_assistant_pb2.DialogStateOut.CLOSE_MICROPHONE
PLAYING = embedded_assistant_pb2.ScreenOutConfig.PLAYING
DEFAULT_GRPC_DEADLINE = 60 *3 + 5


audio_sample_rate  = audio_helpers.DEFAULT_AUDIO_SAMPLE_RATE
audio_sample_width = audio_helpers.DEFAULT_AUDIO_SAMPLE_WIDTH

audio_iter_size    = audio_helpers.DEFAULT_AUDIO_ITER_SIZE
audio_block_size   = audio_helpers.DEFAULT_AUDIO_DEVICE_BLOCK_SIZE
audio_flush_size   = audio_helpers.DEFAULT_AUDIO_DEVICE_FLUSH_SIZE







class RosAssistant(object):
    def __init__(self, device_model_id, device_id, credentials, conversation_stream):
        self.language_code = 'ko-KR'
        self.device_model_id = device_model_id
        self.device_id = device_id
        self.conversation_stream = conversation_stream

        self.pub_move = rospy.Publisher("/GA",String,queue_size=10)
        #self.stop = Twist(0, 0, 0, 0, 0, 0)
        

        self.conversation_state = None
        # Force reset of first conversation.
        self.is_new_conversation = True        
        self.deadline = DEFAULT_GRPC_DEADLINE #if you want to change dealine time, pls change it
        
        print("[class] credentails : ", credentials)

        self.make_grpc_channel(credentials)
        self.assistant = embedded_assistant_pb2_grpc.EmbeddedAssistantStub(
            self.grpc_channel
        )

        print("[KKR] assistant", self.assistant)
        self.deadline = DEFAULT_GRPC_DEADLINE
        self.device_handler = device_helpers.DeviceRequestHandler(self.device_id)
        self.wakeup_word = "Ok Google"
        self.duration = 0.1  # seconds
        self.freq = 440  # Hz

        # Create an authorized gRPC channel.
        

    def __enter__(self):
        return self
    
    def __exit__(self, etype, e, traceback):
        if e:
            return False
        self.conversation_stream.close()

    def make_grpc_channel(self, credentials):
        try:
            with open(credentials, 'r') as f:
                print("[KKR]make grpc channel")
                self.credentials = google.oauth2.credentials.Credentials(token=None,
                                                                    **json.load(f))
                self.http_request = google.auth.transport.requests.Request()
                self.credentials.refresh(self.http_request)
        except Exception as e:
            logging.error('Error loading credentials: %s', e)
            logging.error('Run google-oauthlib-tool to initialize '
                        'new OAuth 2.0 credentials.')
            sys.exit(-1)
        api_endpoint = ASSISTANT_API_ENDPOINT
        # Create an authorized gRPC channel.
        self.grpc_channel = google.auth.transport.grpc.secure_authorized_channel(
            self.credentials, self.http_request, api_endpoint)
        logging.info('[KKR] Connecting to %s', api_endpoint)



    def is_grpc_error_unavailable(e):
        is_grpc_error = isinstance(e, grpc.RpcError)
        if is_grpc_error and (e.code() == grpc.StatusCode.UNAVAILABLE):
            logging.error('grpc unavailable error: %s', e)
            return True
        return False

    def check_wakeup_word(self, request_cmd):
        index = request_cmd.find(self.wakeup_word)
        if index > -1 :
            return True
        else:
            return False



    @retry(reraise= True, stop=stop_after_attempt(1), retry=retry_if_exception(is_grpc_error_unavailable))
    def assist(self):
        continue_conversation = False
        device_actions_futures = []

        self.conversation_stream.start_recording()
        print('Recording audio request')

        def iter_log_assist_requests(): #debugging
            for c in self.gen_assist_request():
                assistant_helpers.log_assist_request_without_audio(c)
                yield c
            logging.debug('Reached end of AssistRequest iteration')

        request_cmd = ''

        for resp in self.assistant.Assist(iter_log_assist_requests(),
                                          self.deadline):
            assistant_helpers.log_assist_response_without_audio(resp)
            if resp.event_type == END_OF_UTTERANCE:
                logging.info('End of audio request detected.')
                logging.info('Stopping recording.')

                self.conversation_stream.stop_recording()
            if resp.speech_results:
                request_cmd = ''.join(r.transcript for r in resp.speech_results)
                rospy.loginfo("[KKR] : %s", request_cmd)

                logging.info('Transcript of user request: "%s".',
                             ' '.join(r.transcript
                                      for r in resp.speech_results))

            if len(resp.audio_out.audio_data) > 0:
                
                index = -1
                isMoving = False
                valid = False
                
                
                if not self.conversation_stream.playing:
                    self.conversation_stream.stop_recording()
                    self.conversation_stream.start_playback()
                    
                    valid = self.check_wakeup_word(request_cmd)
                    if valid :
                        rospy.loginfo("[KKR] : Valid")
                        index = request_cmd.find('??????')
                    else :
                        rospy.loginfo("[KKR] : Invalid")
                        break  
                
                    if index > -1 :
                        #dst = request_cmd.split(' ')[2].decode('utf-8').encode('cp949')
                        self.pub_move.publish(request_cmd)
                        isMoving = True
                        rospy.loginfo("[KKR] : request moving")
                    else :
                        self.pub_move.publish("GA Request")
                
                if isMoving :
                    os.system('play -nq -t alsa synth {} sine {}'.format(self.duration, self.freq))
                    rospy.loginfo("[KKR] : Move to Destination")
                    break
                    
                else :
                    self.conversation_stream.write(resp.audio_out.audio_data)
                

            if resp.dialog_state_out.conversation_state:
                conversation_state = resp.dialog_state_out.conversation_state
                logging.debug('Updating conversation state.')
                self.conversation_state = conversation_state
            if resp.dialog_state_out.volume_percentage != 0:
                volume_percentage = resp.dialog_state_out.volume_percentage
                logging.info('Setting volume to %s%%', volume_percentage)
                self.conversation_stream.volume_percentage = volume_percentage
            if resp.dialog_state_out.microphone_mode == DIALOG_FOLLOW_ON:
                continue_conversation = True
                logging.info('Expecting follow-on query from user.')
            elif resp.dialog_state_out.microphone_mode == CLOSE_MICROPHONE:
                continue_conversation = False
            if resp.device_action.device_request_json:
                device_request = json.loads(
                    resp.device_action.device_request_json
                )
                fs = self.device_handler(device_request)
                if fs:
                    device_actions_futures.extend(fs)
            
        if len(device_actions_futures):
            logging.info('Waiting for device executions to complete.')
            concurrent.futures.wait(device_actions_futures)

        logging.info('Finished playing assistant response.')
        self.conversation_stream.stop_playback()
        return continue_conversation, request_cmd

        
    def gen_assist_request(self):
        """Yields: AssistRequest messages to send to the API."""

        config = embedded_assistant_pb2.AssistConfig(
            audio_in_config=embedded_assistant_pb2.AudioInConfig(
                encoding='LINEAR16',
                sample_rate_hertz=self.conversation_stream.sample_rate,
            ),
            audio_out_config=embedded_assistant_pb2.AudioOutConfig(
                encoding='LINEAR16',
                sample_rate_hertz=self.conversation_stream.sample_rate,
                volume_percentage=self.conversation_stream.volume_percentage,
            ),
            dialog_state_in=embedded_assistant_pb2.DialogStateIn(
                language_code=self.language_code,
                conversation_state=self.conversation_state,
                is_new_conversation=self.is_new_conversation,
            ),
            device_config=embedded_assistant_pb2.DeviceConfig(
                device_id=self.device_id,
                device_model_id=self.device_model_id,
            )
        )

        self.is_new_conversation = False
        # The first AssistRequest must contain the AssistConfig
        # and no audio data.
        yield embedded_assistant_pb2.AssistRequest(config=config)
        for data in self.conversation_stream:
            # Subsequent requests need audio data, but not config.
            yield embedded_assistant_pb2.AssistRequest(audio_in=data)
    

if __name__ == '__main__':

    rospy.init_node('google_assistant_ros', anonymous=True)


    #project_id = rospy.get_param("/google_assistant_ros/device_id")
    #device_id = rospy.get_param("/google_assistant_ros/project_id")

    project_id = "turtlebot-ai-speaker"
    device_id = "turtlebot-ai-speaker-raspi_103-33luii"

    #rospy.loginfo("device model id : %s", device_model_id)
    rospy.loginfo("[main] project id : %s" , project_id)
    rospy.loginfo("[main] device id : %s", device_id)

    rospy.loginfo("test test test test")
    credentials = os.path.join(click.get_app_dir('google-oauthlib-tool'), 'credentials.json')
    rospy.loginfo("[main] - credentials : %s", credentials)

    

    # Configure audio source and sink.

    audio_device = None
    audio_source = audio_device = (
            audio_device or audio_helpers.SoundDeviceStream(
                sample_rate=audio_sample_rate,
                sample_width=audio_sample_width,
                block_size=audio_block_size,
                flush_size=audio_flush_size
            )
        )
    
    audio_sink = audio_device = (
            audio_device or audio_helpers.SoundDeviceStream(
                sample_rate=audio_sample_rate,
                sample_width=audio_sample_width,
                block_size=audio_block_size,
                flush_size=audio_flush_size
            )
        )
        # Create conversation stream with the given audio source and sink.
    conversation_stream = audio_helpers.ConversationStream(
        source=audio_source,
        sink=audio_sink,
        iter_size=audio_iter_size,
        sample_width=audio_sample_width,
    )

    device_config = os.path.join(click.get_app_dir('googlesamples-assistant'), 'device_config.json')

    device_model_id = []
    if not device_id or not device_model_id:
        try:
            with open(device_config) as f:
                device = json.load(f)
                device_id = device['id']
                device_model_id = device['model_id']
                rospy.loginfo("Using device model %s and device id %s", device_model_id, device_id)
        except Exception as e:
            logging.warning("Device config not found : %s" %e)
            logging.info('Registering device')
            if not device_model_id:
                logging.error("Option --device-model-id required" "When registering a device instance")
    
    #self, device_model_id, device_id, credentials,  conversation_stream
    #rospy.loginfo("device model id : %s", device_model_id)
    ros_assistant = RosAssistant(device_model_id, device_id, credentials, conversation_stream)


    pub = rospy.Publisher("GA", String, queue_size=5)
       
    
    while not rospy.is_shutdown():

        try:        
            continue_conversation, request_cmd = ros_assistant.assist()
        except KeyboardInterrupt:
            sys.exit()



        #if once and (not continue_conversation):
        #        break
        #rospy.spin()

