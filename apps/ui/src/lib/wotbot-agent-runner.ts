import { BaseEvent, EventType } from '@ag-ui/client';
import {
  AgentRunnerConnectRequest,
  InMemoryAgentRunner,
} from '@copilotkit/runtime/v2';
import { filter, Observable } from 'rxjs';

/**
 * Keeps graph steps available during a live run while excluding them from
 * connection replay. Steps are transient progress markers; replaying them is
 * unnecessary for chat hydration and can fail when compactEvents() reorders a
 * start/finish pair around overlapping message or tool-call streams.
 */
export class WotbotAgentRunner extends InMemoryAgentRunner {
  override connect(request: AgentRunnerConnectRequest): Observable<BaseEvent> {
    return super
      .connect(request)
      .pipe(
        filter(
          (event) =>
            event.type !== EventType.STEP_STARTED &&
            event.type !== EventType.STEP_FINISHED,
        ),
      );
  }
}
