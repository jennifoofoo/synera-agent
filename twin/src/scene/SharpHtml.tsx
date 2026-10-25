// drei <Html> with whole-pixel placement. drei writes the projected screen point as is (e.g. 625.571px), so Chrome
// composites the label layer at a fractional offset and the text looks smeared. Rounding the point, and centring with
// a 2D translate rounded to whole pixels (text widths are fractional, so -50% alone lands on half pixels) instead of a
// second translate3d layer, keeps map labels and chips sharp. Drop-in for drei's Html.
import type { ComponentProps } from "react";
import { Html as DreiHtml } from "@react-three/drei";
import type { Camera, Object3D } from "three";
import { Vector3 } from "three";

const v = new Vector3();
/** Centre on whole pixels where CSS round() is supported (Chrome 125+, Safari 15.4+), else the plain -50%. */
const CENTRE =
  typeof CSS !== "undefined" && CSS.supports?.("transform", "translate(round(-50%, 1px), round(-50%, 1px))")
    ? "translate(round(-50%, 1px), round(-50%, 1px))"
    : "translate(-50%, -50%)";

/** drei's default projection, rounded to whole CSS pixels. */
export function snapPosition(el: Object3D, camera: Camera, size: { width: number; height: number }): [number, number] {
  v.setFromMatrixPosition(el.matrixWorld).project(camera);
  const w = size.width / 2;
  const h = size.height / 2;
  return [Math.round(v.x * w + w), Math.round(-(v.y * h) + h)];
}

type Props = ComponentProps<typeof DreiHtml>;

export function Html({ center, style, transform, calculatePosition, ...rest }: Props) {
  if (transform) return <DreiHtml center={center} style={style} transform calculatePosition={calculatePosition} {...rest} />;
  return (
    <DreiHtml
      calculatePosition={calculatePosition ?? snapPosition}
      style={center ? { position: "absolute", transform: CENTRE, ...style } : style}
      {...rest}
    />
  );
}
