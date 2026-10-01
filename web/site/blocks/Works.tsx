// <Works>: read by its parent <Scope>, never rendered on its own.
// Port of the retired showcase's only_inside("Scope") registration.

import { onlyInside } from "./shared";

export type WorksProps = Record<string, never>;

export default onlyInside("Scope");
