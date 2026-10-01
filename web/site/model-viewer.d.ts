// <model-viewer> in JSX: the attributes the showcase's blocks set on it, as strings, since
// the server renders them as plain attributes for the custom element to read.

import type { DetailedHTMLProps, HTMLAttributes } from "react";

type ModelViewerAttributes = DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & {
  src?: string;
  loading?: string;
  autoplay?: boolean | "";
  "camera-controls"?: boolean | "";
  "animation-name"?: string;
  "shadow-intensity"?: string;
  "interaction-prompt"?: string;
};

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "model-viewer": ModelViewerAttributes;
    }
  }
}
