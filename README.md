1. Google Assistant 사용법
- gRPC 초기화 
 >>import google.assistant.embedded.v1alpha1.embedded_assistant_pb2_grpc
 >>assistant = embedded_assistant_pb2.EmbeddedAssistantStub(channel)

-Assist streaming method를 부르기. AssistRequest
 >>assist_responses_generator = assistant.Assist(assist_requests_generator)
 >>start_acquiring_audio()

