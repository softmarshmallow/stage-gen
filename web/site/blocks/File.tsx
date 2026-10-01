// <File>: read by its parent <Files>, never rendered on its own.
// Port of the retired showcase's only_inside("Files") registration.

import { onlyInside } from "./shared";

export interface FileProps {
  readonly path: string;
}

export default onlyInside("Files");
