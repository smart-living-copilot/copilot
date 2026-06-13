import { httpJson } from '@/lib/http-client';

export type RuntimeAffordanceType = 'property' | 'action' | 'event';

export async function readRuntimeProperty(
  thingId: string,
  propertyName: string,
  uriVariables?: Record<string, unknown>,
): Promise<unknown> {
  return httpJson('/wot/runtime/read-property', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      thing_id: thingId,
      property_name: propertyName,
      uri_variables: uriVariables,
    }),
  });
}

export async function invokeRuntimeAction(
  thingId: string,
  actionName: string,
  input: unknown,
  uriVariables?: Record<string, unknown>,
): Promise<unknown> {
  return httpJson('/wot/runtime/invoke-action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      thing_id: thingId,
      action_name: actionName,
      input,
      uri_variables: uriVariables,
    }),
  });
}

export async function subscribeRuntimeEvent(
  thingId: string,
  eventName: string,
  subscriptionInput: unknown,
  uriVariables?: Record<string, unknown>,
): Promise<unknown> {
  return httpJson('/wot/runtime/subscribe-event', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      thing_id: thingId,
      event_name: eventName,
      subscription_input: subscriptionInput,
      uri_variables: uriVariables,
    }),
  });
}
