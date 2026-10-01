// <Atlas>: read by its parent <Painter>, never rendered on its own.
// Port of the retired showcase's only_inside("Painter") registration.

import { onlyInside } from "./shared";

export interface AtlasProps {
  readonly output: string;
}

export default onlyInside("Painter");
