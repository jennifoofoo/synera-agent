import * as THREE from "three";

const point = new THREE.Vector3();

/** drei <Html> calculatePosition that snaps to whole CSS pixels. The default leaves fractions ("translate3d(612.37px,
 * …)"), and a text layer composited at a fractional offset is resampled: the label looks blurry. */
export function roundedPosition(el: THREE.Object3D, camera: THREE.Camera, size: { width: number; height: number }): number[] {
  point.setFromMatrixPosition(el.matrixWorld).project(camera);
  const halfW = size.width / 2;
  const halfH = size.height / 2;
  return [Math.round(point.x * halfW + halfW), Math.round(-(point.y * halfH) + halfH)];
}

/** Centre a label on its anchor (and lift it `liftPx` plus its own height above, when `above`) in whole pixels, in
 * place of drei's `center` (translate -50%, half a pixel off for an odd width). Keeps up with size changes. */
export function crispCentre(el: HTMLElement, above: boolean, liftPx: number): () => void {
  const place = () => {
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    const dy = above ? h + liftPx : h / 2;
    el.style.transform = `translate(${-Math.round(w / 2)}px, ${-Math.round(dy)}px)`;
  };
  place();
  const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(place);
  observer?.observe(el);
  return () => {
    observer?.disconnect();
    el.style.transform = ""; // drei's `center` takes over again
  };
}
