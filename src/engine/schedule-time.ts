/**
 * Fire-time resolver for the `schedule` trigger source.
 *
 * The dependency-free core is the single authority. Tests may inject a
 * resolver with `TriggerEngineOptions.scheduleTime`, but the host does not
 * switch implementations at runtime.
 */

import {
  firstScheduledAt,
  nextScheduledAt,
  type ScheduleRule,
} from '../core/triggers/schedule-time.ts'

/** Compute fire instants for one normalized rule. */
export interface ScheduleTime {
  /** First committed target; a recurring rule is strictly after `now`. */
  first(rule: ScheduleRule, now: number): string
  /** Next target strictly after `after`; `undefined` for a one-shot. */
  next(rule: ScheduleRule, after: number): string | undefined
}

/** Default dependency-free resolver. */
export const pureScheduleTime: ScheduleTime = {
  first: firstScheduledAt,
  next: nextScheduledAt,
}
