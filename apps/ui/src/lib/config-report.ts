import {
  parseReasoningEffortLevels,
  type ReasoningEffortConfig,
} from './reasoning-effort';

/** One allowlisted setting, as reported by the backend's `GET /api/config`. */
export interface ConfigField {
  name: string;
  value: string | number | boolean | null;
  configured: boolean;
  is_default: boolean;
  secret: boolean;
  note: string | null;
}

export interface ConfigSection {
  key: string;
  title: string;
  fields: ConfigField[];
}

export interface ConfigReport {
  version: string;
  sections: ConfigSection[];
}

export function findField(
  report: ConfigReport,
  name: string,
): ConfigField | null {
  for (const section of report.sections) {
    const match = section.fields.find((field) => field.name === name);
    if (match) {
      return match;
    }
  }
  return null;
}

export interface ConfigMismatch {
  setting: string;
  uiValue: string;
  backendValue: string;
}

function formatLevels(levels: string[]): string {
  return levels.length ? levels.join(', ') : 'none';
}

/**
 * Compare what the UI believes about reasoning effort against what the agent
 * resolved.
 *
 * These are the one group of settings read twice from two different process
 * environments -- `reasoning-effort-runtime-config.ts` parses them in the UI
 * container, `core/settings.py` parses them in the backend -- so a deploy that
 * updates only one container leaves the selector offering levels the agent will
 * not honour, with nothing to show for it. This is the check that surfaces it.
 */
export function findConfigMismatches(
  report: ConfigReport,
  uiConfig: ReasoningEffortConfig,
): ConfigMismatch[] {
  const mismatches: ConfigMismatch[] = [];

  const enabled = findField(report, 'REASONING_EFFORT_ENABLED');
  if (enabled && enabled.value !== uiConfig.enabled) {
    mismatches.push({
      setting: 'REASONING_EFFORT_ENABLED',
      uiValue: String(uiConfig.enabled),
      backendValue: String(enabled.value),
    });
  }

  const levels = findField(report, 'REASONING_EFFORT_LEVELS');
  if (levels && typeof levels.value === 'string') {
    const backendLevels = parseReasoningEffortLevels(levels.value);
    const differs =
      backendLevels.length !== uiConfig.levels.length ||
      backendLevels.some((level, index) => level !== uiConfig.levels[index]);

    if (differs) {
      mismatches.push({
        setting: 'REASONING_EFFORT_LEVELS',
        uiValue: formatLevels(uiConfig.levels),
        backendValue: formatLevels(backendLevels),
      });
    }
  }

  return mismatches;
}

/** Display form for a reported value; secrets already arrive as placeholders. */
export function formatConfigValue(field: ConfigField): string {
  if (field.value === null || field.value === '') {
    return 'not set';
  }
  return String(field.value);
}
