export type MediaIngressState =
  | 'idle'
  | 'requesting'
  | 'connecting'
  | 'connected'
  | 'error';

export type CameraFacingMode = 'environment' | 'user';

export interface MediaIngressSession {
  state: MediaIngressState;
  localStream: MediaStream | null;
  remoteStream: MediaStream | null;
  error: string | null;
  latestAssistantText: string | null;
  latestUserTranscript: string | null;
  cameraSnapshotCueSeq: number;
  isAssistantResponsePending: boolean;
  cameraFacingMode: CameraFacingMode;
  canSwitchCamera: boolean;
  isMicrophoneMuted: boolean;
  isCameraEnabled: boolean;
  isSwitchingCamera: boolean;
  setMicrophoneMuted: (muted: boolean) => void;
  setCameraEnabled: (enabled: boolean) => void;
  switchCamera: () => Promise<void>;
  start: () => Promise<void>;
  stop: () => void;
}

export interface LiveKitTokenResponse {
  enabled?: boolean;
  url?: string;
  token?: string;
  room?: string;
  participantIdentity?: string;
  agentName?: string;
}

export interface LiveKitTextStreamReader {
  readAll: () => Promise<string>;
  info?: {
    attributes?: Record<string, string | undefined>;
  };
}

export interface LiveKitParticipantInfo {
  identity?: string;
  kind?: string | number;
  name?: string;
}
