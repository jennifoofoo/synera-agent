// "Walk with me": pedestrian dead reckoning snapped to the known route. See README.md in this folder.
export { createWalkWithMe } from "./walkWithMe";
export type { WalkWithMe, WalkWithMeOptions, WalkEvents } from "./walkWithMe";
export { requestMotionPermission, motionSupport, needsPermissionPrompt } from "./sensors";
export { legsFromRoute, legsFromSegments } from "./legs";
export { RouteMatcher } from "./routeMatcher";
export type { RouteMatcherOptions, ResetTarget } from "./routeMatcher";
export { StepDetector, detectSteps, stepLength, DEFAULT_STEP_LENGTH_M } from "./stepDetector";
export { HeadingSmoother, headingFromOrientation, angleDiff, modelBearing, modelToCompass } from "./heading";
export type * from "./types";
