import { useMemo } from "react";
import type { Route } from "../api/types";
import { avoidsLine, closedOnRoute } from "../model/closures";
import type { BuildingModel } from "../model/model";
import { useTwin } from "../store";

/** One quiet line under the route facts when something on the route's floors is closed: "Avoids closed Lift 1".
 * The server routes around every closure, so the line is true whenever it shows; gone at once on reopening. */
export function AvoidsClosed({ model, route }: { model: BuildingModel; route: Route }) {
  const closed = useTwin((s) => s.state?.closed);
  const text = useMemo(() => avoidsLine(closedOnRoute(model, route, closed ?? [])), [model, route, closed]);
  return text ? (
    <div className="route-avoids" data-testid="route-avoids">
      {text}
    </div>
  ) : null;
}
