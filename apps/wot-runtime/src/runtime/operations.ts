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
import { createRuntimeError, formatError, isDataSchemaError } from '../services/errors.js';
import { getAffordanceDefinition, getFormHttpMethod, resolveFormIndex } from '../services/form-selection.js';
import { getRuntimeHealth } from '../services/runtime-health.js';
import axios from 'axios';

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

function interactionError(operation: string, thingId: string, affordanceName: string, error: unknown): never {
  if (isDataSchemaError(error) || formatError(error) === 'Invalid value according to DataSchema') {
    throw createRuntimeError(
      'invalid_argument',
      `${operation} input for '${thingId}/${affordanceName}' does not match the Thing Description schema. ` +
        `Check the affordance input schema and pass a matching value, or remove the input schema for a no-argument action. ` +
        `Original error: ${formatError(error)}`,
    );
  }
  throw error;
}

function schemaIncludesType(schema: Record<string, unknown>, expectedType: string): boolean {
  const type = schema.type;
  if (type === expectedType) {
    return true;
  }
  return Array.isArray(type) && type.includes(expectedType);
}

function actionInputSchema(actionDef: unknown): Record<string, unknown> | null {
  if (!isPlainObject(actionDef) || !isPlainObject(actionDef.input)) {
    return null;
  }
  return actionDef.input;
}

function objectInputRequiredFields(actionDef: unknown): string[] | null {
  const schema = actionInputSchema(actionDef);
  if (!schema || !schemaIncludesType(schema, 'object')) {
    return null;
  }
  return Array.isArray(schema.required)
    ? schema.required.filter((field): field is string => typeof field === 'string' && field.trim().length > 0)
    : [];
}

/**
 * Defaults omitted optional object action inputs to an empty object.
 */
export function resolveInvokeActionInput(actionDef: unknown, input: unknown): unknown {
  const requiredFields = objectInputRequiredFields(actionDef);
  if (requiredFields === null) {
    return input;
  }
  if ((input === undefined || input === null) && requiredFields.length === 0) {
    return {};
  }
  return input;
}

/**
 * Builds a clear validation message for omitted required object action inputs.
 */
export function missingInvokeActionInputMessage(
  actionDef: unknown,
  thingId: string,
  actionName: string,
  input: unknown,
): string | null {
  if (input !== undefined && input !== null) {
    return null;
  }

  const requiredFields = objectInputRequiredFields(actionDef);
  if (!requiredFields?.length) {
    return null;
  }

  return (
    `InvokeAction input for '${thingId}/${actionName}' must be an object with required ` +
    `field${requiredFields.length === 1 ? '' : 's'}: ${requiredFields.join(', ')}. ` +
    `Pass an object matching the Thing Description input schema.`
  );
}

/**
 * Returns whether an action is marked `safe` in its Thing Description and is
 * therefore idempotent enough to cache its result.
 */
export function isCacheableSafeAction(actionDef: unknown): boolean {
  return isPlainObject(actionDef) && actionDef.safe === true;
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
  const result = await thing
    .readProperty(propertyName, options)
    .catch((error: unknown) => interactionError('ReadProperty', thingId, propertyName, error));

  const payload = await encodeInteractionOutputPayload(result, {
    onInvalidSchema: () => {
      log.warn(`Property '${propertyName}' returned data that failed schema validation, returning raw value`);
    },
  });

  return buildEncodedInteractionResponse({ body: payload.body, contentType: payload.contentType }, payload.contentType);
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
  await thing
    .writeProperty(propertyName, input, options)
    .catch((error: unknown) => interactionError('WriteProperty', thingId, propertyName, error));

  return buildInteractionResponse(undefined);
}

/**
 * Checks if a form has an MCP tool binding.
 */
function getMcpToolName(document: ThingDescription, actionName: string, formIndex: number | undefined): string | null {
  try {
    const actionDef = getAffordanceDefinition(document, actionName, 'invokeaction');
    if (!isPlainObject(actionDef)) return null;
    const forms = (actionDef as Record<string, unknown>).forms;
    if (!Array.isArray(forms)) return null;
    const idx = typeof formIndex === 'number' ? formIndex : 0;
    const form = forms[idx];
    if (!isPlainObject(form)) return null;
    const mcpTool = (form as Record<string, unknown>)['mcp:tool'];
    return typeof mcpTool === 'string' && mcpTool.trim() ? mcpTool.trim() : null;
  } catch {
    return null;
  }
}

/**
 * Resolves the MCP server endpoint URL from a form href + document base.
 */
function resolveMcpEndpoint(document: ThingDescription, actionName: string, formIndex: number | undefined): string {
  const actionDef = getAffordanceDefinition(document, actionName, 'invokeaction');
  if (!isPlainObject(actionDef)) {
    throw createRuntimeError('invalid_argument', `Cannot resolve MCP endpoint for '${actionName}'`);
  }
  const forms = (actionDef as Record<string, unknown>).forms;
  if (!Array.isArray(forms)) {
    throw createRuntimeError('invalid_argument', `No forms found for action '${actionName}'`);
  }
  const idx = typeof formIndex === 'number' ? formIndex : 0;
  const form = forms[idx];
  if (!isPlainObject(form)) {
    throw createRuntimeError('invalid_argument', `No form at index ${idx} for action '${actionName}'`);
  }
  const href = (form as Record<string, unknown>).href;
  if (typeof href !== 'string' || !href) {
    throw createRuntimeError('invalid_argument', `Form href is missing for action '${actionName}'`);
  }
  // Resolve relative href against the document's base URL
  const base = typeof document.base === 'string' ? document.base : '';
  try {
    return new URL(href, base).href;
  } catch {
    throw createRuntimeError('invalid_argument', `Cannot resolve MCP endpoint href='${href}' base='${base}'`);
  }
}

/**
 * In-memory cache for MCP sessions: endpoint → sessionId.
 * Sessions are reused across multiple tool calls within the same runtime lifetime.
 */
const mcpSessionCache = new Map<string, string>();

/**
 * MCP headers required for Streamable HTTP transport.
 */
const MCP_HEADERS = {
  'Content-Type': 'application/json',
  'Accept': 'application/json, text/event-stream',
  'mcp-protocol-version': '2025-03-26',
};

/**
 * Parses an SSE (Server-Sent Events) response and extracts the JSON payload
 * from the first "data:" line inside an "event: message" block.
 */
function parseSseToJson(sseText: string): any {
  const dataMatch = sseText.match(/event:\s*message\s*\n\s*data:\s*(\{.*\})/s);
  if (dataMatch) {
    try {
      return JSON.parse(dataMatch[1]);
    } catch {
      // fall through
    }
  }
  // Fallback: try parsing raw text as JSON
  try {
    return JSON.parse(sseText);
  } catch {
    return null;
  }
}

/**
 * Initializes an MCP session if one is not already cached.
 * Uses JSON-RPC 2.0 "initialize" to create a session and returns the session ID.
 */
async function ensureMcpSession(endpoint: string): Promise<string> {
  const cached = mcpSessionCache.get(endpoint);
  if (cached) {
    return cached;
  }

  const initPayload = {
    jsonrpc: '2.0',
    method: 'initialize',
    params: {
      protocolVersion: '2025-03-26',
      capabilities: {},
      clientInfo: { name: 'wot-runtime', version: '1.0.0' },
    },
    id: 'init-1',
  };

  log.info(`MCP initialize session on ${endpoint}`);
  const response = await axios.post(endpoint, initPayload, {
    headers: MCP_HEADERS,
    responseType: 'text',
    timeout: 30_000,
    validateStatus: () => true,
  });

  if (response.status >= 400) {
    const body = parseSseToJson(response.data) || response.data;
    const errorMsg = body?.error?.message || body?.error || String(body).substring(0, 500);
    throw createRuntimeError('unknown', `MCP initialize failed [${response.status}]: ${errorMsg}`);
  }

  // Extract session ID from response headers
  const sessionId = response.headers['mcp-session-id'];
  if (!sessionId) {
    log.info('MCP server did not return a session ID; assuming stateless');
    mcpSessionCache.set(endpoint, '__stateless__');
    return '__stateless__';
  }

  log.info(`MCP session established: ${sessionId}`);
  mcpSessionCache.set(endpoint, sessionId);
  return sessionId;
}

/**
 * Builds MCP request headers including session ID if available.
 */
function buildMcpHeaders(sessionId: string): Record<string, string> {
  const headers: Record<string, string> = { ...MCP_HEADERS };
  if (sessionId && sessionId !== '__stateless__') {
    headers['mcp-session-id'] = sessionId;
  }
  return headers;
}

/**
 * Performs an MCP JSON-RPC call, handling SSE responses and session management.
 * Handles Streamable HTTP transport: POST returns 200 (inline SSE) or 202 (accepted, GET to poll).
 */
async function mcpCall(
  endpoint: string,
  method: string,
  params: Record<string, unknown>,
  sessionId: string,
): Promise<any> {
  const payload = {
    jsonrpc: '2.0',
    method,
    params,
    id: crypto.randomUUID(),
  };

  let response = await axios.post(endpoint, payload, {
    headers: buildMcpHeaders(sessionId),
    responseType: 'text',
    timeout: 60_000,
    validateStatus: (status) => status === 200 || status === 202,
  });

  // Streamable HTTP: 202 Accepted means the result needs a GET to poll
  if (response.status === 202) {
    log.debug(`MCP 202 Accepted for ${method}, polling via GET`);
    await new Promise((resolve) => setTimeout(resolve, 500));
    response = await axios.get(endpoint, {
      headers: buildMcpHeaders(sessionId),
      responseType: 'text',
      timeout: 60_000,
      validateStatus: () => true,
    });
  }

  // Parse SSE or JSON response
  const body = parseSseToJson(response.data);

  if (!body) {
    throw createRuntimeError('unknown', `MCP: could not parse response: ${String(response.data).substring(0, 500)}`);
  }

  if (response.status >= 400) {
    const errorMsg = body?.error?.message || body?.error || String(response.data).substring(0, 500);
    throw createRuntimeError('unknown', `MCP server error [${response.status}]: ${errorMsg}`);
  }

  if (body?.error) {
    const errorMsg = typeof body.error === 'object'
      ? body.error.message || JSON.stringify(body.error)
      : String(body.error);
    throw createRuntimeError('unknown', `MCP error: ${errorMsg}`);
  }

  return body.result;
}

/**
 * Handles an MCP (Model Context Protocol) action invocation via JSON-RPC 2.0.
 */
async function handleMcpAction(
  document: ThingDescription,
  thingId: string,
  actionName: string,
  mcpToolName: string,
  input: unknown,
  formIndex: number | undefined,
): Promise<any> {
  const endpoint = resolveMcpEndpoint(document, actionName, formIndex);
  const mcpInput = isPlainObject(input) ? (input as Record<string, unknown>) : {};

  // Ensure MCP session is initialized
  const sessionId = await ensureMcpSession(endpoint);

  log.info(`MCP call: ${mcpToolName} on ${endpoint}`);

  const result = await mcpCall(endpoint, 'tools/call', { name: mcpToolName, arguments: mcpInput }, sessionId);

  const content = result?.content;

  if (Array.isArray(content) && content.length > 0) {
    const textItems = content.filter((c: any) => c?.type === 'text').map((c: any) => c.text);
    if (textItems.length > 0) {
      const combined = textItems.join('\n');
      const mcpBody = Buffer.from(combined, 'utf-8');
      return {
        completedResult: buildEncodedInteractionResponse({ body: mcpBody, contentType: 'application/json' }).response,
      };
    }
    const mcpBody = Buffer.from(JSON.stringify(content), 'utf-8');
    return {
      completedResult: buildEncodedInteractionResponse({ body: mcpBody, contentType: 'application/json' }).response,
    };
  }

  const mcpBody = Buffer.from(JSON.stringify(result ?? {}), 'utf-8');
  return {
    completedResult: buildEncodedInteractionResponse({ body: mcpBody, contentType: 'application/json' }).response,
  };
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
  const actionDef = getAffordanceDefinition(document, actionName, 'invokeaction');
  const decodedInput = decodePayloadEnvelope(request.input);
  const missingInputMessage = missingInvokeActionInputMessage(actionDef, thingId, actionName, decodedInput);
  if (missingInputMessage) {
    throw createRuntimeError('invalid_argument', missingInputMessage);
  }
  const resolvedInput = resolveInvokeActionInput(actionDef, decodedInput);

  // GET/HEAD requests must not carry a body (RFC 9110). For HTTP forms bound to
  // these methods, an action's input travels via uriVariables (kept in
  // options), so we drop the body here — otherwise node-wot tries to send it
  // and the request fails. Non-GET/HEAD and non-HTTP forms are unaffected.
  const httpMethod = getFormHttpMethod(document, actionName, 'invokeaction', resolvedFormIndex);
  const bodilessMethod = httpMethod === 'GET' || httpMethod === 'HEAD';
  if (bodilessMethod && resolvedInput !== undefined) {
    log.debug(`Dropping body for ${httpMethod} action '${thingId}/${actionName}'; input flows via uriVariables`);
  }
  const input = bodilessMethod ? undefined : resolvedInput;

  // MCP (Model Context Protocol) support: if the action's form has an
  // "mcp:tool" property, route the call through JSON-RPC 2.0 to the
  // MCP server instead of using node-wot.
  const mcpToolName = getMcpToolName(document, actionName, resolvedFormIndex);
  if (mcpToolName) {
    return handleMcpAction(document, thingId, actionName, mcpToolName, resolvedInput, resolvedFormIndex);
  }

  // Special handling for downloadAsset: the action uses GET but needs to pass
  // the EDR authorization token as an HTTP header. node-wot drops the body for
  // GET requests (RFC 9110), and the credential system injects the portal API
  // token — not the EDR token. So we make a direct HTTP request here.
  // Also handles the case where input is a JSON string (common agent mistake).
  let dlInput = decodedInput;
  if (actionName === 'downloadAsset' && typeof dlInput === 'string') {
    try { dlInput = JSON.parse(dlInput); } catch { /* not JSON, ignore */ }
  }
  if (actionName === 'downloadAsset' && isPlainObject(dlInput)) {
    const dlEndpoint = String((dlInput as Record<string, unknown>).endpoint || '');
    const dlAuth = String((dlInput as Record<string, unknown>).authorization || '');
    if (dlEndpoint && dlAuth) {
      log.info(`Direct HTTP GET for downloadAsset at ${dlEndpoint}`);
      const dlResponse = await axios.get(dlEndpoint, {
        headers: { Authorization: dlAuth },
        responseType: 'arraybuffer',
        validateStatus: () => true,
      });
      const dlBody = Buffer.from(dlResponse.data);
      const dlContentType = String(dlResponse.headers['content-type'] || 'application/octet-stream');
      return {
        completedResult: buildEncodedInteractionResponse(
          { body: dlBody, contentType: dlContentType },
          dlContentType,
        ).response,
      };
    }
  }

  if (isPlainObject(actionDef) && actionDef.synchronous === false) {
    throw createRuntimeError(
      'unimplemented',
      `Action '${actionName}' declares synchronous=false and query/cancel support is not implemented yet`,
    );
  }

  const isCacheable = isCacheableSafeAction(actionDef);
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

  const result = await (
    input === undefined
      ? thing.invokeAction(actionName, undefined, options)
      : thing.invokeAction(actionName, input, options)
  ).catch((error: unknown) => interactionError('InvokeAction', thingId, actionName, error));

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
      ).catch((error) =>
        log.warn(`Cache write failed for invokeAction '${thingId}/${actionName}': ${formatError(error)}`),
      );
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
