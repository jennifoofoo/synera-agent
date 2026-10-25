import { useMemo } from "react";
import type { Route } from "../api/types";
import { avoidsLine, closedOnRoute } from "../model/closures";
import { untilText } from "../model/facts";
import type { BuildingModel } from "../model/model";
import { useTwin } from "../store";

/** One quiet line under the route facts when something on the route's floors is closed: "Avoids closed Lift 1".
 * The server routes around every closure, so the line is true whenever it shows; gone at once on reopening.
 * A timed closure names its end: "Avoids closed Lift 1 until tomorrow 18:00". */
export function AvoidsClosed({ model, route }: { model: BuildingModel; route: Route }) {
  const closed = useTwin((s) => s.state?.closed);
  const closedUntil = useTwin((s) => s.state?.closed_until);
  const text = useMemo(() => {
    const until = Object.fromEntries(Object.entries(closedUntil ?? {}).map(([id, end]) => [id, untilText(end)]));
    return avoidsLine(closedOnRoute(model, route, closed ?? [], until));
  }, [model, route, closed, closedUntil]);
  return text ? (
    <div className="route-avoids" data-testid="route-avoids">
      {text}
    </div>
  ) : null;
}
