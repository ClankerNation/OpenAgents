/**
 * Event subscription and decoding utilities for OpenAgentsSDK.
 *
 * @fix-author Gaotax2006
 * @date 2026-06-23
 * @issue #144 Add event subscription and decoding to OpenAgentsSDK
 */

export {
  createEventDecoder,
  subscribeToEvent,
  decodeHistoricalEvents,
} from "./subscription";
export type { DecodedEvent, SubscriptionHandle } from "./subscription";
