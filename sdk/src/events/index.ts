/**
 * @fix-author scotia1973-bot
 *
 * Events module for the OpenAgents SDK.
 * Provides event log decoding and subscription management.
 */

export {
  decodeEventLog,
  decodeEventLogs,
  filterEventsByName,
  filterEventsByAddress,
  findEventByName,
  eventSignature,
  eventSignatureHash,
  buildEventMap,
} from "./decoder";

export type {
  AbiEventInputType,
  AbiEventInput,
  AbiEvent,
  DecodedEventParam,
  DecodedEvent,
  LogEntry,
  LogDecodeOptions,
} from "./decoder";

export {
  EventSubscriptionManager,
  createEventFilter,
} from "./subscription";

export type {
  SubscriptionFilter,
  SubscriptionConfig,
  ActiveSubscription,
  EventCallback,
} from "./subscription";
