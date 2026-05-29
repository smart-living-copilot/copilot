import log from '../logger/index.js';
import { annotateThingDescriptionSecurityNames } from '../runtime/credentials.js';
import { getWotClient } from '../runtime/servient.js';
import { buildCacheKey, getCached, setCached } from '../services/cache.js';
import { fetchThingDescription, type ThingDescription } from '../services/thing-catalog-client.js';
import {
  decodePayloadEnvelope,
  encodeInteractionOutputPayload,
  encodePayloadEnvelope,
  normalizeBody,
} from '../services/payloads.js';
import { createRuntimeError, formatError } from '../services/errors.js';
import { getAffordanceDefinition, resolveFormIndex } from '../services/form-selection.js';
import { getRuntimeHealth } from '../services/runtime-health.js';


/**
 * Checks if a value is a plain object.
 */
function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

/**
 * Extracts the thingId from a runtime request.
 */
function getRequestedThingId(request: any): string {
  return String(request?.target?.thingId || request?.thingId || '').trim();
}

/**
 * Decodes URI variables from a runtime request.
 */
function decodeUriVariables(uriVariables: any[] | undefined): Record<string, unknown> {
  const entries = Array.isArray(uriVariables) ? uriVariables : [];
  const values: Record<string, unknown> = {};

  for (const entry of entries) {
    const name = String(entry?.name || '').trim();
    if (!name) {
      continue;
    }
    values[name] = decodePayloadEnvelope(entry.value);
  }

  return values;
}

/**
 * Builds interaction options (uriVariables, formIndex) for node-wot.
 */
function buildInteractionOptions(request: any, resolvedFormIndex?: number): Record<string, unknown> | undefined {
  const options: Record<string, unknown> = {};
  const uriVariables = decodeUriVariables(request.uriVariables);

  if (Object.keys(uriVariables).length > 0) {
    options.uriVariables = uriVariables;
  }

  const formIndex = resolvedFormIndex ?? request?.formSelector?.formIndex;
  if (typeof formIndex === 'number' && Number.isInteger(formIndex)) {
    options.formIndex = formIndex;
  }

  return Object.keys(options).length === 0 ? undefined : options;
}

/**
 * Builds a standardized interaction response object from an encoded payload.
 */
function buildEncodedInteractionResponse(
  payload: { body: Buffer; contentType: string },
  responseContentType?: string,
): { response: any } {
  const normalizedResponseContentType = responseContentType || payload.contentType || 'application/json';

  return {
    response: {
      payload: {
        body: payload.body,
        contentType: payload.contentType,
      },
      responseContentType: normalizedResponseContentType,
      matchedAdditionalResponse: false,
      success: true,
      statusCode: 200,
      statusText: 'ok',
      chosenForm: {},
    },
  };
}

/**
 * Builds a standardized interaction response object from a high-level value.
 */
function buildInteractionResponse(value: unknown, contentType?: string): { response: any } {
  const payload = encodePayloadEnvelope(value, contentType);
  return buildEncodedInteractionResponse(
    {
      body: normalizeBody(payload.body),
      contentType: String(payload.contentType || contentType || 'application/json'),
    },
    contentType || String(payload.contentType || 'application/json'),
  );
}


/**
 * Fetches a Thing Description and consumes it via the node-wot servient.
 */
async function consumeThing(request: any): Promise<{
  thing: any;
  document: ThingDescription;
  hash: string;
}> {
  const thingId = getRequestedThingId(request);
  if (!thingId) {
    throw createRuntimeError('invalid_argument', 'thing_id is required');
  }

  const { document, hash } = await fetchThingDescription(thingId).catch((error) => {
    throw createRuntimeError('not_found', formatError(error));
  });

  annotateThingDescriptionSecurityNames(document);
  const wot = await getWotClient();
  const thing = await wot.consume(document);

  return { thing, document, hash };
}

/**
 * Handles a request to retrieve a Thing Description.
 *
 * @param request The runtime request containing the thingId.
 */
export async function handleGetThingDescription(request: any): Promise<any> {
  const thingId = String(request?.thingId || '').trim();
  if (!thingId) {
    throw createRuntimeError('invalid_argument', 'thing_id is required');
  }

  const { document, hash } = await fetchThingDescription(thingId).catch((error) => {
    throw createRuntimeError('not_found', formatError(error));
  });

  return {
    thingId,
    thingDescription: encodePayloadEnvelope(document, 'application/td+json'),
    tdHash: hash,
  };
}

/**
 * Handles a ReadProperty interaction.
 *
 * @param request The runtime request containing target and options.
 */
export async function handleReadProperty(request: any): Promise<any> {
  const thingId = getRequestedThingId(request);
  const propertyName = String(request?.target?.affordanceName || '').trim();
  if (!propertyName) {
    throw createRuntimeError('invalid_argument', 'target.affordance_name is required for ReadProperty');
  }

  const { thing, document } = await consumeThing(request);
  if (!getAffordanceDefinition(document, propertyName, 'readproperty')) {
    throw createRuntimeError('not_found', `Thing '${thingId}' does not define property '${propertyName}'`);
  }

  const resolvedFormIndex = (() => {
    try {
      return resolveFormIndex(document, propertyName, 'readproperty', request?.formSelector);
    } catch (error) {
      throw createRuntimeError('invalid_argument', formatError(error));
    }
  })();

  const options = buildInteractionOptions(request, resolvedFormIndex);
  const result = await thing.readProperty(propertyName, options);

  const payload = await encodeInteractionOutputPayload(result, {
    onInvalidSchema: () => {
      log.warn(`Property '${propertyName}' returned data that failed schema validation, returning raw value`);
    },
  });

  return buildEncodedInteractionResponse(
    { body: payload.body, contentType: payload.contentType },
    payload.contentType,
  );
}

/**
 * Handles a WriteProperty interaction.
 *
 * @param request The runtime request containing target, input, and options.
 */
export async function handleWriteProperty(request: any): Promise<any> {
  const thingId = getRequestedThingId(request);
  const propertyName = String(request?.target?.affordanceName || '').trim();
  if (!propertyName) {
    throw createRuntimeError('invalid_argument', 'target.affordance_name is required for WriteProperty');
  }

  const input = decodePayloadEnvelope(request.input);
  if (input === undefined) {
    throw createRuntimeError('invalid_argument', 'input payload is required for WriteProperty');
  }

  const { thing, document } = await consumeThing(request);
  if (!getAffordanceDefinition(document, propertyName, 'writeproperty')) {
    throw createRuntimeError('not_found', `Thing '${thingId}' does not define property '${propertyName}'`);
  }

  const resolvedFormIndex = (() => {
    try {
      return resolveFormIndex(document, propertyName, 'writeproperty', request?.formSelector);
    } catch (error) {
      throw createRuntimeError('invalid_argument', formatError(error));
    }
  })();

  const options = buildInteractionOptions(request, resolvedFormIndex);
  await thing.writeProperty(propertyName, input, options);

  return buildInteractionResponse(undefined);
}

/**
 * Handles an InvokeAction interaction.
 *
 * @param request The runtime request containing target, input, and options.
 */
export async function handleInvokeAction(request: any): Promise<any> {
  const thingId = getRequestedThingId(request);
  const actionName = String(request?.target?.affordanceName || '').trim();
  if (!actionName) {
    throw createRuntimeError('invalid_argument', 'target.affordance_name is required for InvokeAction');
  }

  const { thing, document } = await consumeThing(request);
  if (!getAffordanceDefinition(document, actionName, 'invokeaction')) {
    throw createRuntimeError('not_found', `Thing '${thingId}' does not define action '${actionName}'`);
  }

  const resolvedFormIndex = (() => {
    try {
      return resolveFormIndex(document, actionName, 'invokeaction', request?.formSelector);
    } catch (error) {
      throw createRuntimeError('invalid_argument', formatError(error));
    }
  })();

  const options = buildInteractionOptions(request, resolvedFormIndex) || {};
  const input = decodePayloadEnvelope(request.input);
  const actionDef = getAffordanceDefinition(document, actionName, 'invokeaction');

  if (isPlainObject(actionDef) && actionDef.synchronous === false) {
    throw createRuntimeError(
      'unimplemented',
      `Action '${actionName}' declares synchronous=false and query/cancel support is not implemented yet`,
    );
  }

  const isCacheable = isPlainObject(actionDef) && actionDef.safe === true;
  const uriVariables = decodeUriVariables(request.uriVariables);
  const cacheKey = isCacheable ? buildCacheKey(thingId, 'invoke_action', actionName, uriVariables, input) : '';

  if (isCacheable) {
    const cached = await getCached(cacheKey);
    if (cached) {
      log.info(`Cache hit for invokeAction '${thingId}/${actionName}'`);
      return {
        completedResult: buildEncodedInteractionResponse(
          { body: Buffer.from(cached.payload, 'base64'), contentType: cached.contentType },
          cached.contentType,
        ).response,
      };
    }
  }

  const result =
    input === undefined
      ? await thing.invokeAction(actionName, undefined, options)
      : await thing.invokeAction(actionName, input, options);

  if (result) {
    const payload = await encodeInteractionOutputPayload(result, {
      onInvalidSchema: () => {
        log.warn(`Action '${actionName}' returned data that failed output schema validation, returning raw value`);
      },
    });
    const interactionResponse = buildEncodedInteractionResponse(
      { body: payload.body, contentType: payload.contentType },
      payload.contentType,
    );

    if (isCacheable) {
      await setCached(
        cacheKey,
        { contentType: payload.contentType, payload: payload.body.toString('base64'), statusCode: 200 },
        payload.body.length,
      ).catch((error) => log.warn(`Cache write failed for invokeAction '${thingId}/${actionName}': ${formatError(error)}`));
    }

    return { completedResult: interactionResponse.response };
  }

  return {
    completedResult: buildInteractionResponse(undefined).response,
  };
}

/**
 * Handles a health check request, returning the status of various runtime components.
 */
export async function handleGetRuntimeHealth(): Promise<any> {
  const health = await getRuntimeHealth();

  return {
    status: health.status,
    servientReady: health.servientReady,
    backendReachable: health.backendReachable,
    valkeyConfigured: health.valkeyConfigured,
    protocols: health.protocols,
    startedAt: health.startedAt || '',
  };
}
