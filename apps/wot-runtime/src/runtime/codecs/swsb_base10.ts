/**
 * Version of the payload parser logic.
 */
const payload_parser_version = [1, 3, 3];

/**
 * Mapping of error codes to human-readable strings.
 */
const ERROR_CODE: Record<number, string> = {
  0: 'VALVE_DRIVE_READY',
  1: 'VALVE_DRIVE_UNINITIALIZED',
  2: 'VALVE_TO_TIGHT',
  3: 'ADJUST_RANGE_OVERSIZE',
  4: 'ADJUST_RANGE_UNDERSIZE',
  5: 'ADAPTION_RUN_CALC_ERROR',
};

/**
 * Mapping of device active modes to human-readable strings.
 */
const ACTIVE_MODE: Record<number, string> = {
  0: 'Manu Temp',
  1: 'Manu_Pos',
  2: 'Auto',
  3: 'Emergency',
  4: 'Frost Protection',
  5: 'Boost',
  6: 'Window Open',
  7: 'Holiday',
};

/**
 * Mapping of weekday indices to names.
 */
const WEEKDAY: Record<number, string> = {
  0: 'SUNDAY',
  1: 'MONDAY',
  2: 'TUESDAY',
  3: 'WEDNESDAY',
  4: 'THURSDAY',
  5: 'FRIDAY',
  6: 'SATURDAY',
};

/**
 * Mapping of month indices to names.
 */
const MONTH: Record<number, string> = {
  0: 'JANUARY',
  1: 'FEBRUARY',
  2: 'MARCH',
  3: 'APRIL',
  4: 'MAY',
  5: 'JUNE',
  6: 'JULY',
  7: 'AUGUST',
  8: 'SEPTEMBER',
  9: 'OCTOBER',
  10: 'NOVEMBER',
  11: 'DECEMBER',
};

/**
 * Mapping of week-of-month indices to labels.
 */
const WEEK_OF_MONTH: Record<number, string> = {
  1: '1st',
  2: '2nd',
  3: '3rd',
  4: '4th',
  5: 'last',
};

/**
 * Mapping of data rate indices to labels.
 */
const DATA_RATE: Record<number, string> = {
  0: 'Adaptive Data Rate',
  1: 'DR 0',
  2: 'DR 1',
  3: 'DR 2',
  4: 'DR 3',
  5: 'DR 4',
  6: 'DR 5',
};

/**
 * Mapping of rejoin behavior indices to labels.
 */
const REJOIN_BEHAVIOR: Record<number, string> = {
  1: 'Cyclic Rejoin',
  0: 'Single Rejoin',
};

/**
 * Mapping of command IDs to human-readable names.
 */
const COMMAND_ID: Record<number, string> = {
  0: 'COMMAND_ID_GET_STATUS_INTERVAL',
  1: 'COMMAND_ID_SET_STATUS_INTERVAL',
  2: 'COMMAND_ID_GET_STATUS_PARAMETER_TX_ENABLE_REGISTER',
  3: 'COMMAND_ID_SET_STATUS_PARAMETER_TX_ENABLE_REGISTER',
  4: 'COMMANF_ID_GET_STATUS',
  5: 'COMMAND_ID_GET_BATTERY_VOLTAGE',
  6: 'COMMAND_ID_GET_BATTTERY_COVER_LOCK_STATUS',
  7: 'COMMAND_ID_GET_ERROR_CODE',
  8: 'COMMAND_ID_GET_DEVICE_TIME',
  9: 'COMMAND_ID_SET_DEVICE_TIME',
  10: 'COMMAND_ID_GET_DEVICE_TIME_CONFIG',
  11: 'COMMAND_ID_SET_DEVICE_TIME_CONFIG',
  12: 'COMMAND_ID_GET_MODE_STATUS',
  13: 'COMMAND_ID_SET_MANU_TEMPERATURE_MODE',
  14: 'COMMAND_ID_SET_MANU_POSITIONING_MODE',
  15: 'COMMAND_ID_SET_AUTO_MODE',
  16: 'COMMAND_ID_SET_HOLIDAY_MODE',
  17: 'COMMAND_ID_SET_BOOST_MODE',
  18: 'COMMAND_ID_GET_HOLIDAY_MODE_CONFIG',
  19: 'COMMAND_ID_DISABLE_HOLIDAY_MODE',
  20: 'COMMAND_ID_GET_BOOST_CONFIG',
  21: 'COMMAND_ID_SET_BOOST_CONFIG',
  22: 'COMMAND_ID_GET_WEEK_PROGRAM',
  23: 'COMMAND_ID_SET_WEEK_PROGRAM',
  24: 'COMMAND_ID_GET_VALVE_POSITION',
  25: 'COMMAND_ID_GET_VALVE_SET_POINT_POSITION',
  26: 'COMMAND_ID_SET_VALVE_SET_POINT_POSITION',
  27: 'COMMAND_ID_GET_VALVE_OFFSET',
  28: 'COMMAND_ID_SET_VALVE_OFFSET',
  29: 'COMMAND_ID_GET_VALVE_MAXIMUM_POSITION',
  30: 'COMMAND_ID_SET_VALVE_MAXIMUM_POSITION',
  31: 'COMMAND_ID_GET_VALVE_EMERGENCY_POSITION',
  32: 'COMMAND_ID_SET_VALVE_EMERGENCY_POSITION',
  33: 'COMMAND_ID_GET_SET_POINT_TEMPERATURE',
  34: 'COMMAND_ID_SET_SET_POINT_TEMPERATURE',
  35: 'COMMAND_ID_SET_EXTERNAL_ROOM_TEMPERATURE',
  36: 'COMMAND_ID_GET_TEMPERATURE_OFFSET',
  37: 'COMMAND_ID_SET_TEMPERATURE_OFFSET',
  38: 'COMMAND_ID_GET_HEATING_CNTRL_INPUT_ROOM_TEMPERATURE',
  39: 'COMMAND_ID_GET_HEATING_CNTRL_INPUT_SET_POINT_TEMPERATURE',
  40: 'COMMAND_ID_GET_HEATING_CNTRL_CONFIG',
  41: 'COMMAND_ID_SET_HEATING_CNTRL_CONFIG',
  42: 'COMMAND_ID_GET_HEATING_CNTRL_STATIC_GAINS',
  43: 'COMMAND_ID_SET_HEATING_CNTRL_STATTC_GAINS',
  44: 'COMMAND_ID_GET_HEATING_CNTRL_INPUT_GAINS',
  45: 'COMMAND_ID_RESET_HEATING_CONTROLLER_ADAPTIVE_GAINS',
  46: 'COMMAND_ID_GET_WINDOW_OPEN_STATUS',
  47: 'COMMAND_ID_SET_WINDOW_OPEN_STATUS',
  48: 'COMMAND_ID_GET_WINDOW_OPEN_DETECTION_CONFIG',
  49: 'COMMAND_ID_SET_WINDOW_OPEN_DETECTION_CONFIG',
  50: 'COMMAND_ID_GET_DECALCIFICATION_CONFIG',
  51: 'COMMAND_ID_SET_DECALCIFICATION_CONFIG',
  52: 'COMMAND_ID_PERFORM_ADAPTION_RUN',
  53: 'COMMAND_ID_PERFORM_DECALCIFICATION',
  54: 'COMMAND_ID_COMMAND_FAILED',
  55: 'COMMAND_ID_SET_BUTTON_ACTION',
  56: 'COMMAND_ID_GET_BUTTON_ACTION',
  57: 'COMMAND_ID_SET_HARDWARE_LOCK',
  58: 'COMMAND_ID_GET_HARDWARE_LOCK',
  59: 'COMMAND_ID_GET_DISPLAY_CONFIG',
  60: 'COMMAND_ID_SET_DISPLAY_CONFIG',
  116: 'COMMAND_ID_GET_COPRO_VERSION',
  119: 'COMMAND_ID_GET_REMAINING_TIME_UNTIL_REJOIN',
  120: 'COMMAND_ID_GET_DATA_RATE',
  121: 'COMMAND_ID_SET_DATA_RATE',
  122: 'COMMAND_ID_GET_REJOIN_BEHAVIOR',
  123: 'COMMAND_ID_SET_REJOIN_BEHAVIOR',
  124: 'COMMAND_ID_GET_ALL_CONFIG',
  125: 'COMMAND_ID_PERFORM_FACTORY_RESET',
  126: 'COMMAND_ID_PERFORM_SOFTWARE_RESET',
  127: 'COMMAND_ID_GET_VERSION',
};

/**
 * Represents the structure of a decoded SWSB payload.
 */
export interface SWSBData {
  status_report?: {
    interval?: { value: number; unit: string };
  };
  radio?: {
    status_report?: {
      parameter_tx_enable_reg?: {
        battery_voltage_enabled: boolean;
        room_temperature_enabled: boolean;
        set_point_temperature_enabled: boolean;
        valve_position_enabled: boolean;
        controller_gains_enabled: boolean;
        device_flags_enabled: boolean;
        unit: string;
      };
    };
    failed_commands?: { value: Record<number, string>; unit: string };
    data_rate?: { value: string; unit: string };
    cyclic_rejoin?: {
      remaining_time_until_rejoin?: { value: number; unit: string };
      conf?: { value: string; unit: string };
      interval?: { value: number; unit: string };
    };
  };
  battery_voltage?: { value: string; unit: string };
  heating_control?: {
    room_temperature?: { value: string; unit: string };
    set_point_temperature?: { value: string; unit: string };
    valve_position?: { value: string; unit: string };
    gain?: {
      p?: { value: number };
      i?: { value: number };
      unit: string;
    };
    mode?: {
      active_mode?: { value: string; unit: string };
      active_main_mode?: { value: string; unit: string };
      holiday?: {
        is_active?: { value: boolean; unit: string };
        is_pending?: { value: boolean; unit: string };
        begin?: any;
        end?: any;
        set_point_temperature?: { value: string; unit: string };
      };
      boost?: {
        is_active?: { value: boolean; unit: string };
        config?: {
          duration?: { value: number; unit: string };
          valve_position?: { value: string; unit: string };
        };
      };
      frost_protection?: { is_active?: { value: boolean; unit: string } };
      window_open_detection?: {
        is_active?: { value: boolean; unit: string };
        is_open?: { value: boolean; unit: string };
        config?: any;
      };
      emergency?: {
        is_active?: { value: boolean; unit: string };
        config?: { valve_set_point_position?: { value: string; unit: string } };
      };
      auto?: {
        selected_week_program?: { value: number; unit: string };
        week_program_1?: any;
        week_program_2?: any;
        week_program_3?: any;
      };
      manu_pos?: { valve_set_point_position?: { value: string; unit: string } };
      manu_temp?: { value: string; unit: string };
    };
    config?: {
      valve?: {
        position_offset?: { value: string; unit: string };
        max_position?: { value: string; unit: string };
      };
      temperature?: { offset?: { value: string; unit: string } };
      adaptive_gain_adjustment_enabled?: { value: boolean; unit: string };
      controller_temperature_input_select?: { value: boolean; unit: string };
      static_gain?: {
        p?: { value: number };
        i?: { value: number };
        unit: string;
      };
      decalcification_time?: {
        weekday?: { value: string; unit: string };
        week_of_month?: { value: string; unit: string };
        hour?: { value: number; unit: string };
        minute?: { value: number; unit: string };
      };
    };
    input_gain?: {
      p?: { value: number };
      i?: { value: number };
      unit: string;
    };
  };
  battery_cover_locked?: { value: boolean; unit: string };
  error_code?: { value: string; unit: string };
  device_time?: {
    local?: any;
    config?: any;
  };
  button_action?: {
    single_tap?: { value: string };
    double_tap?: { value: string };
    unit?: string;
    hw_factory_reset_locked?: { value: boolean; unit: string };
    hw_set_point_temp_locked?: { value: boolean; unit: string };
    hw_system_button_locked?: { value: boolean; unit: string };
  };
  display?: {
    orientation?: { value: number; unit: string };
    color_inversion?: { value: boolean; unit: string };
    en_legacy_temp_scale?: { value: boolean; unit: string };
  };
  version?: {
    application_copro?: { value: Record<number, number>; unit: string };
    bootloader_copro?: { value: Record<number, number>; unit: string };
    hw_revision?: { value: number; unit: string };
    application?: { value: Record<number, number>; unit: string };
    bootloader?: { value: Record<number, number>; unit: string };
    lorawan_l2?: { value: Record<number, number>; unit: string };
    payload_parser?: { value: Record<number, number>; unit: string };
  };
}

/**
 * Input structure for the decoder.
 */
export interface DecoderInput {
  bytes: number[];
  fPort: number;
}

/**
 * Decodes a LoRaWAN uplink payload for the SWSB device.
 *
 * @param input Object containing the raw bytes.
 * @returns Decoded data object.
 */
export function decodeUplink(input: DecoderInput): SWSBData {
  const data: SWSBData = {};
  let idx = 0;

  const commandId = input.bytes[idx++];
  switch (COMMAND_ID[commandId]) {
    case 'COMMAND_ID_GET_STATUS_INTERVAL':
      data.status_report = {
        interval: { value: input.bytes[idx] * 30 + 30, unit: 's' },
      };
      break;
    case 'COMMAND_ID_GET_STATUS_PARAMETER_TX_ENABLE_REGISTER': {
      const statusParamTxEnableRegister = input.bytes[idx];
      data.radio = {
        status_report: {
          parameter_tx_enable_reg: {
            battery_voltage_enabled: !!(statusParamTxEnableRegister & (1 << 7)),
            room_temperature_enabled: !!(statusParamTxEnableRegister & (1 << 6)),
            set_point_temperature_enabled: !!(statusParamTxEnableRegister & (1 << 5)),
            valve_position_enabled: !!(statusParamTxEnableRegister & (1 << 4)),
            controller_gains_enabled: !!(statusParamTxEnableRegister & (1 << 3)),
            device_flags_enabled: !!(statusParamTxEnableRegister & (1 << 2)),
            unit: 'bool',
          },
        },
      };
      break;
    }
    case 'COMMANF_ID_GET_STATUS': {
      const statusParamTxStatus = input.bytes[idx++];

      if (statusParamTxStatus & (1 << 7)) {
        data.battery_voltage = {
          value: (input.bytes[idx++] * 10 + 1500).toFixed(0),
          unit: 'mV',
        };
      }

      if (statusParamTxStatus & (1 << 6)) {
        data.heating_control = data.heating_control || {};
        data.heating_control.room_temperature = {
          value: (((input.bytes[idx] << 8) | input.bytes[idx + 1]) * 0.1).toFixed(1),
          unit: '°C',
        };
        idx += 2;
      }

      if (statusParamTxStatus & (1 << 5)) {
        data.heating_control = data.heating_control || {};
        data.heating_control.set_point_temperature = {
          value: (input.bytes[idx++] * 0.5).toFixed(1),
          unit: '°C',
        };
      }

      if (statusParamTxStatus & (1 << 4)) {
        data.heating_control = data.heating_control || {};
        data.heating_control.valve_position = {
          value: (input.bytes[idx++] * 0.5).toFixed(1),
          unit: '%',
        };
      }

      if (statusParamTxStatus & (1 << 3)) {
        data.heating_control = data.heating_control || {};
        data.heating_control.gain = {
          p: { value: (input.bytes[idx++] << 8) + input.bytes[idx++] },
          i: { value: input.bytes[idx++] / 1000000 },
          unit: 'uint',
        };
      }

      if (statusParamTxStatus & (1 << 2)) {
        data.heating_control = data.heating_control || {};
        const device_flags = input.bytes[idx];
        data.heating_control.mode = {
          active_mode: { value: ACTIVE_MODE[(device_flags & 0xe0) >> 5], unit: 'string' },
          holiday: { is_pending: { value: !!(device_flags & (1 << 4)), unit: 'bool' } },
          window_open_detection: { is_open: { value: !!(device_flags & (1 << 3)), unit: 'bool' } },
        };
      }
      break;
    }
    case 'COMMAND_ID_GET_BATTERY_VOLTAGE':
      data.battery_voltage = {
        value: (input.bytes[idx] * 10 + 1500).toFixed(0),
        unit: 'mV',
      };
      break;
    case 'COMMAND_ID_GET_BATTTERY_COVER_LOCK_STATUS':
      data.battery_cover_locked = {
        value: !!(input.bytes[idx] & 0x01),
        unit: 'bool',
      };
      break;
    case 'COMMAND_ID_GET_ERROR_CODE':
      data.error_code = {
        value: ERROR_CODE[input.bytes[idx]],
        unit: 'string',
      };
      break;
    case 'COMMAND_ID_GET_DEVICE_TIME':
      data.device_time = {
        local: {
          second: { value: input.bytes[idx++] & 0x1f, unit: 's' },
          minute: { value: (input.bytes[idx] >> 2) & 0x3f, unit: 'min' },
          hour: { value: ((input.bytes[idx++] & 0x03) << 3) + (input.bytes[idx] >> 5), unit: 'h' },
          day: { value: input.bytes[idx++] & 0x1f, unit: 'd' },
          is_dst: { value: !!(input.bytes[idx] & 0x80), unit: 'bool' },
          weekday: { value: WEEKDAY[(input.bytes[idx] >> 4) & 0x07], unit: 'string' },
          month: { value: MONTH[input.bytes[idx++] & 0x0f], unit: 'string' },
          year: { value: input.bytes[idx++] + 2000, unit: 'a' },
          utc_offset: { value: (input.bytes[idx] * 0.25 - 12).toFixed(2), unit: 'h' },
        },
      };
      break;
    case 'COMMAND_ID_GET_DEVICE_TIME_CONFIG':
      data.device_time = {
        config: {
          auto_time_sync_en: { value: !!(input.bytes[idx] >> 7), unit: 'bool' },
          utc_offset: { value: ((input.bytes[idx++] & 0x7f) * 0.25 - 12).toFixed(2), unit: 'h' },
          utc_dst_begin: {
            week_of_month: { value: WEEK_OF_MONTH[(input.bytes[idx] >> 4) & 0x0f], unit: 'string' },
            month: { value: MONTH[input.bytes[idx++] & 0x0f], unit: 'string' },
            weekday: { value: WEEKDAY[input.bytes[idx] >> 5], unit: 'string' },
            hour: { value: input.bytes[idx++] & 0x0f, unit: 'h' },
            minute: { value: (input.bytes[idx] >> 4) * 5, unit: 'min' },
          },
          utc_dst_offset: { value: ((input.bytes[idx++] & 0x7f) * 0.25 - 12).toFixed(2), unit: 'h' },
          utc_dst_end: {
            week_of_month: { value: WEEK_OF_MONTH[(input.bytes[idx] >> 4) & 0x0f], unit: 'string' },
            month: { value: MONTH[input.bytes[idx++] & 0x0f], unit: 'string' },
            weekday: { value: WEEKDAY[input.bytes[idx] >> 5], unit: 'string' },
            hour: { value: input.bytes[idx++] & 0x0f, unit: 'h' },
            minute: { value: (input.bytes[idx] & 0x0f) * 5, unit: 'min' },
          },
        },
      };
      break;
    case 'COMMAND_ID_GET_MODE_STATUS':
      data.heating_control = {
        mode: {
          active_main_mode: { value: ACTIVE_MODE[input.bytes[idx] >> 6], unit: 'string' },
          holiday: {
            is_active: { value: !!(input.bytes[idx] & (1 << 5)), unit: 'bool' },
            is_pending: { value: !!(input.bytes[idx] & (1 << 4)), unit: 'bool' },
          },
          boost: { is_active: { value: !!(input.bytes[idx] & (1 << 3)), unit: 'bool' } },
          frost_protection: { is_active: { value: !!(input.bytes[idx] & (1 << 2)), unit: 'bool' } },
          window_open_detection: { is_active: { value: !!(input.bytes[idx] & (1 << 1)), unit: 'bool' } },
          emergency: { is_active: { value: !!(input.bytes[idx++] & (1 << 0)), unit: 'bool' } },
          auto: { selected_week_program: { value: input.bytes[idx] >> 6, unit: 'uint' } },
        },
      };
      break;
    case 'COMMAND_ID_GET_HOLIDAY_MODE_CONFIG':
      data.heating_control = {
        mode: {
          holiday: {
            begin: {
              minute: { value: ((input.bytes[idx] >> 2) & 0x0f) * 5, unit: 'min' },
              hour: { value: ((input.bytes[idx++] & 0x03) << 3) + (input.bytes[idx] >> 5), unit: 'h' },
              day: { value: input.bytes[idx++] & 0x1f, unit: 'd' },
              month: { value: MONTH[input.bytes[idx] >> 4], unit: 'string' },
              year: { value: input.bytes[idx++] + 2000, unit: 'a' },
            },
            end: {
              minute: { value: ((input.bytes[idx] >> 2) & 0x0f) * 5, unit: 'min' },
              hour: { value: ((input.bytes[idx++] & 0x03) << 3) + (input.bytes[idx] >> 5), unit: 'h' },
              day: { value: input.bytes[idx++] & 0x1f, unit: 'd' },
              month: { value: MONTH[input.bytes[idx++] & 0x0f], unit: 'string' },
              year: { value: input.bytes[idx++] + 2000, unit: 'a' },
            },
            set_point_temperature: { value: (input.bytes[idx] * 0.5).toFixed(1), unit: '°C' },
          },
        },
      };
      break;
    case 'COMMAND_ID_GET_BOOST_CONFIG':
      data.heating_control = {
        mode: {
          boost: {
            config: {
              duration: { value: input.bytes[idx++] * 15, unit: 's' },
              valve_position: { value: (input.bytes[idx] * 0.5).toFixed(0), unit: '%' },
            },
          },
        },
      };
      break;
    case 'COMMAND_ID_GET_WEEK_PROGRAM': {
      const week_program_nbr = (input.bytes[idx] >> 4) & 0x03;
      const nbr_time_switching_points = input.bytes[idx++] & 0x0f;
      const programs: any[] = [];

      for (let i = 0; i < nbr_time_switching_points; i++) {
        programs.push({
          minute: (input.bytes[idx] >> 4) * 5,
          hour: ((input.bytes[idx++] & 0x0f) << 1) + (input.bytes[idx] >> 7),
          weekdays: input.bytes[idx++] & 0x7f,
          set_point_temperature: parseFloat((input.bytes[idx++] * 0.5).toFixed(1)),
        });
      }

      data.heating_control = {
        mode: {
          auto: {
            [`week_program_${week_program_nbr + 1}`]: programs,
          },
        },
      };
      break;
    }
    case 'COMMAND_ID_GET_VALVE_POSITION':
      data.heating_control = {
        valve_position: { value: (input.bytes[idx] * 0.5).toFixed(0), unit: '%' },
      };
      break;
    case 'COMMAND_ID_GET_VALVE_SET_POINT_POSITION':
      data.heating_control = {
        mode: { manu_pos: { valve_set_point_position: { value: (input.bytes[idx] * 0.5).toFixed(0), unit: '%' } } },
      };
      break;
    case 'COMMAND_ID_GET_VALVE_OFFSET':
      data.heating_control = {
        config: { valve: { position_offset: { value: (input.bytes[idx] * 0.5).toFixed(0), unit: '%' } } },
      };
      break;
    case 'COMMAND_ID_GET_VALVE_MAXIMUM_POSITION':
      data.heating_control = {
        config: { valve: { max_position: { value: (input.bytes[idx] * 0.5).toFixed(0), unit: '%' } } },
      };
      break;
    case 'COMMAND_ID_GET_VALVE_EMERGENCY_POSITION':
      data.heating_control = {
        mode: {
          emergency: {
            config: { valve_set_point_position: { value: (input.bytes[idx] * 0.5).toFixed(0), unit: '%' } },
          },
        },
      };
      break;
    case 'COMMAND_ID_GET_SET_POINT_TEMPERATURE':
      data.heating_control = {
        mode: { manu_temp: { value: (input.bytes[idx] * 0.5).toFixed(1), unit: '°C' } },
      };
      break;
    case 'COMMAND_ID_GET_TEMPERATURE_OFFSET':
      data.heating_control = {
        config: { temperature: { offset: { value: (input.bytes[idx] * 0.1 - 12.8).toFixed(1), unit: 'K' } } },
      };
      break;
    case 'COMMAND_ID_GET_HEATING_CNTRL_INPUT_ROOM_TEMPERATURE':
      data.heating_control = {
        room_temperature: { value: (((input.bytes[idx] << 8) | input.bytes[idx + 1]) * 0.1).toFixed(1), unit: '°C' },
      };
      break;
    case 'COMMAND_ID_GET_HEATING_CNTRL_INPUT_SET_POINT_TEMPERATURE':
      data.heating_control = {
        set_point_temperature: { value: (input.bytes[idx] * 0.5).toFixed(1), unit: '°C' },
      };
      break;
    case 'COMMAND_ID_GET_HEATING_CNTRL_CONFIG':
      data.heating_control = {
        config: {
          adaptive_gain_adjustment_enabled: { value: !!(input.bytes[idx] & (1 << 7)), unit: 'bool' },
          controller_temperature_input_select: { value: !!(input.bytes[idx] & (1 << 6)), unit: 'bool' },
        },
      };
      break;
    case 'COMMAND_ID_GET_HEATING_CNTRL_STATIC_GAINS':
      data.heating_control = {
        config: {
          static_gain: {
            p: { value: (input.bytes[idx++] << 8) + input.bytes[idx++] },
            i: { value: input.bytes[idx] / 1000000 },
            unit: 'uint',
          },
        },
      };
      break;
    case 'COMMAND_ID_GET_HEATING_CNTRL_INPUT_GAINS':
      data.heating_control = {
        input_gain: {
          p: { value: (input.bytes[idx++] << 8) + input.bytes[idx++] },
          i: { value: input.bytes[idx] / 1000000 },
          unit: 'uint',
        },
      };
      break;
    case 'COMMAND_ID_GET_WINDOW_OPEN_STATUS':
      data.heating_control = {
        mode: { window_open_detection: { is_open: { value: !!(input.bytes[idx] & 0x01), unit: 'bool' } } },
      };
      break;
    case 'COMMAND_ID_GET_WINDOW_OPEN_DETECTION_CONFIG': {
      data.heating_control = {
        mode: {
          window_open_detection: {
            config: {
              source: { value: !!(input.bytes[idx] & (1 << 3)), unit: 'bool' },
              enable_mode: {
                holiday: { value: !!(input.bytes[idx] & (1 << 0)) },
                auto: { value: !!(input.bytes[idx] & (1 << 1)) },
                manu_temp: { value: !!(input.bytes[idx++] & (1 << 2)) },
                unit: 'bool',
              },
              open_duration: { value: (input.bytes[idx] >> 5) * 10 + 10, unit: 'min' },
              temperature_delta: { value: ((input.bytes[idx++] & 0x1f) * 0.1 + 0.5).toFixed(1), unit: 'K' },
              open_temperature: { value: (input.bytes[idx] * 0.5).toFixed(1), unit: '°C' },
            },
          },
        },
      };
      break;
    }
    case 'COMMAND_ID_GET_DECALCIFICATION_CONFIG':
      data.heating_control = {
        config: {
          decalcification_time: {
            weekday: { value: WEEKDAY[input.bytes[idx] >> 4], unit: 'string' },
            week_of_month: { value: WEEK_OF_MONTH[(input.bytes[idx] >> 1) & 0x07], unit: 'string' },
            hour: { value: ((input.bytes[idx++] & 0x01) << 4) + (input.bytes[idx] >> 4), unit: 'h' },
            minute: { value: (input.bytes[idx] & 0x0f) * 5, unit: 'min' },
          },
        },
      };
      break;
    case 'COMMAND_ID_COMMAND_FAILED': {
      const nbr_failed_commands = input.bytes[idx++];
      const failed: Record<number, string> = {};
      for (let i = 0; i < nbr_failed_commands; i++) {
        failed[i] = COMMAND_ID[input.bytes[idx++]];
      }
      data.radio = { failed_commands: { value: failed, unit: 'COMMAND_ID' } };
      break;
    }
    case 'COMMAND_ID_GET_BUTTON_ACTION':
      data.button_action = {
        single_tap: { value: COMMAND_ID[input.bytes[idx++]] },
        double_tap: { value: COMMAND_ID[input.bytes[idx]] },
        unit: 'COMMAND_ID',
      };
      break;
    case 'COMMAND_ID_GET_HARDWARE_LOCK':
      data.button_action = {
        hw_factory_reset_locked: { value: !!(input.bytes[idx] & 0x01), unit: 'bool' },
        hw_set_point_temp_locked: { value: !!((input.bytes[idx] >> 1) & 0x01), unit: 'bool' },
        hw_system_button_locked: { value: !!((input.bytes[idx] >> 1) & 0x01), unit: 'bool' },
      };
      break;
    case 'COMMAND_ID_GET_DISPLAY_CONFIG':
      data.display = {
        orientation: { value: (input.bytes[idx] & 0x03) * 90, unit: '°' },
        color_inversion: { value: !!((input.bytes[idx] >> 2) & 0x01), unit: 'bool' },
        en_legacy_temp_scale: { value: !!((input.bytes[idx] >> 3) & 0x01), unit: 'bool' },
      };
      break;
    case 'COMMAND_ID_GET_DATA_RATE':
      data.radio = { data_rate: { value: DATA_RATE[input.bytes[idx] & 0x0f], unit: 'string' } };
      break;
    case 'COMMAND_ID_GET_COPRO_VERSION':
      data.version = {
        application_copro: {
          value: { 0: input.bytes[idx++], 1: input.bytes[idx++], 2: input.bytes[idx] },
          unit: 'uint',
        },
        bootloader_copro: {
          value: { 0: input.bytes[idx++], 1: input.bytes[idx++], 2: input.bytes[idx] },
          unit: 'uint',
        },
      };
      break;
    case 'COMMAND_ID_GET_REMAINING_TIME_UNTIL_REJOIN':
      data.radio = {
        cyclic_rejoin: {
          remaining_time_until_rejoin: {
            value: ((input.bytes[idx++] & 0x1f) << 16) + (input.bytes[idx++] << 8) + input.bytes[idx],
            unit: 'min',
          },
        },
      };
      break;
    case 'COMMAND_ID_GET_REJOIN_BEHAVIOR':
      data.radio = {
        cyclic_rejoin: {
          conf: { value: REJOIN_BEHAVIOR[Number(!(input.bytes[idx] >> 7))], unit: 'string' },
          interval: { value: (input.bytes[idx++] & 0x7f) * 255 + input.bytes[idx], unit: 'h' },
        },
      };
      break;
    case 'COMMAND_ID_GET_VERSION':
      data.version = {
        hw_revision: { value: input.bytes[idx++], unit: 'uint' },
        application: { value: { 0: input.bytes[idx++], 1: input.bytes[idx++], 2: input.bytes[idx] }, unit: 'uint' },
        bootloader: { value: { 0: input.bytes[idx++], 1: input.bytes[idx++], 2: input.bytes[idx] }, unit: 'uint' },
        lorawan_l2: { value: { 0: input.bytes[idx++], 1: input.bytes[idx++], 2: input.bytes[idx] }, unit: 'uint' },
        payload_parser: {
          value: { 0: payload_parser_version[0], 1: payload_parser_version[1], 2: payload_parser_version[2] },
          unit: 'uint',
        },
      };
      break;
  }

  return data;
}

/**
 * Decodes a hex string representing an SWSB uplink payload.
 *
 * @param hexString The hex-encoded string to decode.
 * @returns The decoded data.
 */
export function decodeHexString(hexString: string): SWSBData {
  const cleanHex = hexString.replace(/^"|"$/g, '').trim();
  const bytes = Buffer.from(cleanHex, 'hex');
  return decodeUplink({ bytes: Array.from(bytes), fPort: 10 });
}

const SWSB_BASE10_MEDIA_TYPE = 'application/vnd.swsb-base10+octet-stream';

/**
 * Recursively decodes a value using schema annotations to identify SWSB-encoded fields.
 *
 * @param value The value to decode.
 * @param schema The JSON Schema definition for the value.
 * @returns The decoded value.
 */
function schemaDrivenDecode(value: any, schema: any): any {
  if (!value || !schema) return value;

  if (schema.encoded === 'swsb-data10' && typeof value === 'string') {
    try {
      return decodeHexString(value);
    } catch (e) {
      console.warn('Failed to decode annotated property:', e);
      return value;
    }
  }

  if (typeof value === 'object' && !Array.isArray(value) && schema.type === 'object' && schema.properties) {
    const newValue = { ...value };
    for (const key in value) {
      if (schema.properties[key]) {
        newValue[key] = schemaDrivenDecode(value[key], schema.properties[key]);
      }
    }
    return newValue;
  }

  if (Array.isArray(value) && schema.type === 'array' && schema.items) {
    return value.map((item) => schemaDrivenDecode(item, schema.items));
  }

  return value;
}

/**
 * Node-WoT ContentCodec for SWSB Base10 binary format.
 */
export default class SWSBBase10 {
  private mediaType: string;

  /**
   * Creates an instance of SWSBBase10.
   *
   * @param mediaType The media type handled by this codec.
   */
  constructor(mediaType: string = SWSB_BASE10_MEDIA_TYPE) {
    this.mediaType = mediaType;
  }

  /**
   * Defines which Content-Type this codec handles.
   *
   * @returns The media type.
   */
  getMediaType(): string {
    return this.mediaType;
  }

  /**
   * Decodes binary data (Buffer) into a JS Object.
   *
   * @param buffer The raw binary data.
   * @param schema Optional JSON Schema for the data.
   * @param _parameters Optional parameters.
   * @returns The decoded value.
   */
  bytesToValue(buffer: Buffer, schema?: any, _parameters?: any): any {
    const text = buffer.toString('utf8').trim();

    try {
      const json = JSON.parse(text);
      if (schema) {
        return schemaDrivenDecode(json, schema);
      }
      return json;
    } catch (err) {
      if (this.mediaType === SWSB_BASE10_MEDIA_TYPE) {
        const input: DecoderInput = {
          bytes: Array.from(buffer),
          fPort: 10,
        };
        return decodeUplink(input);
      }
      throw err;
    }
  }

  /**
   * Encodes a JS Object into binary data (Buffer).
   *
   * @param value The value to encode.
   * @param _schema Optional JSON Schema.
   * @param _parameters Optional parameters.
   * @returns The encoded binary data.
   */
  valueToBytes(value: any, _schema?: any, _parameters?: any): Buffer {
    let body = '';
    if (value !== undefined) {
      body = JSON.stringify(value);
    }
    return Buffer.from(body);
  }
}
