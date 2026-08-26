"use client";

import "ol/ol.css";

import { useEffect, useRef } from "react";
import Feature from "ol/Feature.js";
import OlMap from "ol/Map.js";
import View from "ol/View.js";
import { defaults as defaultControls } from "ol/control/defaults.js";
import { getCenter } from "ol/extent.js";
import Point from "ol/geom/Point.js";
import ImageLayer from "ol/layer/Image.js";
import VectorLayer from "ol/layer/Vector.js";
import type { EventsKey } from "ol/events.js";
import { unByKey } from "ol/Observable.js";
import Projection from "ol/proj/Projection.js";
import ImageStatic from "ol/source/ImageStatic.js";
import VectorSource from "ol/source/Vector.js";
import CircleStyle from "ol/style/Circle.js";
import Fill from "ol/style/Fill.js";
import Stroke from "ol/style/Stroke.js";
import Style from "ol/style/Style.js";
import Text from "ol/style/Text.js";
import {
  imagePixelToMapCoordinate,
  screenPixelsPerImagePixel,
  sortFeaturesByLabelPriority,
  type IllustratedMapFeatureV1,
  type IllustratedMapLabelPlacement,
  type IllustratedMapManifestV1,
} from "@/lib/illustrated-map/contract";
import {
  adjustConstrainedWheelZoom,
  classifyWheelNavigation,
  panCenterFromCurrentView,
} from "@/lib/illustrated-map/wheel-navigation";
import styles from "./UniverseDemo.module.css";

export interface AtlasViewportProps {
  readonly manifest: IllustratedMapManifestV1;
  readonly raster_url: string;
  readonly selected_feature_id: string | null;
  readonly fit_request: number;
  readonly on_select: (featureId: string | null) => void;
}

interface AtlasRuntime {
  readonly destroy: () => void;
  readonly fit: () => void;
  readonly setSelection: (featureId: string | null) => void;
}

function labelOffset(placement: IllustratedMapLabelPlacement): {
  offsetX: number;
  offsetY: number;
  textAlign: CanvasTextAlign;
} {
  switch (placement) {
    case "above":
      return { offsetX: 0, offsetY: -19, textAlign: "center" };
    case "below":
      return { offsetX: 0, offsetY: 21, textAlign: "center" };
    case "left":
      return { offsetX: -16, offsetY: 1, textAlign: "right" };
    case "right":
      return { offsetX: 16, offsetY: 1, textAlign: "left" };
  }
}

function makeFeatureStyle(
  mapFeature: IllustratedMapFeatureV1,
  selected: boolean,
  labelVisible: boolean,
): Style {
  const offset = labelOffset(mapFeature.label.placement);
  return new Style({
    image: new CircleStyle({
      radius: selected ? 8 : 5.5,
      fill: new Fill({
        color: selected ? "#00ff88" : "#111111",
      }),
      stroke: new Stroke({
        color: selected ? "#072d1c" : "#f2f2f2",
        width: selected ? 3 : 2,
      }),
    }),
    text: labelVisible
      ? new Text({
          text: mapFeature.label.fallback_text,
          offsetX: offset.offsetX,
          offsetY: offset.offsetY,
          textAlign: offset.textAlign,
          font: selected
            ? "700 14px ui-monospace, SFMono-Regular, Consolas, monospace"
            : "600 13px ui-monospace, SFMono-Regular, Consolas, monospace",
          fill: new Fill({ color: "#111111" }),
          stroke: new Stroke({ color: "rgba(250, 250, 250, 0.96)", width: 4 }),
          padding: [2, 3, 2, 3],
        })
      : undefined,
    zIndex: selected ? 1000 : mapFeature.label.priority,
  });
}

function createAtlasRuntime(
  target: HTMLElement,
  props: AtlasViewportProps,
  onSelect: (featureId: string | null) => void,
): AtlasRuntime {
  const { manifest } = props;
  const { width, height } = manifest.coordinate_space;
  const extent: [number, number, number, number] = [0, 0, width, height];
  const projection = new Projection({
    code: `illustrated-map:${manifest.map_id}:${manifest.revision}`,
    units: "pixels",
    extent,
  });

  let selectedFeatureId: string | null = props.selected_feature_id;
  const styleCache = new globalThis.Map<string, Style>();
  const featuresById = new globalThis.Map<string, Feature<Point>>();
  const orderedMapFeatures = [...manifest.features].sort(sortFeaturesByLabelPriority);
  const vectorFeatures = orderedMapFeatures.map((mapFeature) => {
    const feature = new Feature({
      geometry: new Point(
        imagePixelToMapCoordinate(mapFeature.geometry.coordinates, height),
      ),
      map_feature: mapFeature,
      priority: mapFeature.label.priority,
    });
    feature.setId(mapFeature.feature_id);
    featuresById.set(mapFeature.feature_id, feature);
    return feature;
  });

  const vectorSource = new VectorSource({ features: vectorFeatures });
  const vectorLayer = new VectorLayer({
    source: vectorSource,
    declutter: true,
    updateWhileAnimating: true,
    updateWhileInteracting: true,
    renderOrder: (left, right) =>
      Number(right.get("priority")) - Number(left.get("priority")),
    style: (feature, resolution) => {
      const mapFeature = feature.get("map_feature") as IllustratedMapFeatureV1;
      const selected = mapFeature.feature_id === selectedFeatureId;
      const labelVisible =
        selected ||
        screenPixelsPerImagePixel(resolution) >=
          mapFeature.label.min_screen_pixels_per_image_pixel;
      const cacheKey = `${mapFeature.feature_id}:${selected ? 1 : 0}:${labelVisible ? 1 : 0}`;
      let style = styleCache.get(cacheKey);
      if (!style) {
        style = makeFeatureStyle(mapFeature, selected, labelVisible);
        styleCache.set(cacheKey, style);
      }
      return style;
    },
  });

  const view = new View({
    projection,
    center: getCenter(extent),
    extent,
    showFullExtent: true,
    smoothExtentConstraint: false,
    constrainOnlyCenter: false,
    enableRotation: false,
    minResolution: 1 / manifest.initial_view.max_screen_pixels_per_image_pixel,
    maxResolution: 1 / manifest.initial_view.min_screen_pixels_per_image_pixel,
  });

  const map = new OlMap({
    target,
    controls: defaultControls({ attribution: false, rotate: false }),
    layers: [
      new ImageLayer({
        source: new ImageStatic({
          url: props.raster_url,
          projection,
          imageExtent: extent,
          interpolate: true,
        }),
      }),
      vectorLayer,
    ],
    view,
  });

  const handleWheelNavigation = (event: WheelEvent) => {
    event.preventDefault();
    event.stopPropagation();

    const intent = classifyWheelNavigation(
      {
        ctrl_key: event.ctrlKey,
        shift_key: event.shiftKey,
        delta_x: event.deltaX,
        delta_y: event.deltaY,
        delta_mode: event.deltaMode,
      },
      map.getSize()?.[1] ?? target.clientHeight,
    );
    if (intent.kind === "ignore") {
      return;
    }

    if (view.getAnimating()) {
      view.cancelAnimations();
    }

    if (intent.kind === "zoom") {
      const anchor = map.getCoordinateFromPixel(map.getEventPixel(event));
      adjustConstrainedWheelZoom(view, intent.delta_zoom_levels, anchor);
      return;
    }

    const center = view.getCenter();
    const resolution = view.getResolution();
    if (!center || resolution === undefined) {
      return;
    }
    view.setCenter(
      panCenterFromCurrentView(
        [center[0], center[1]],
        intent.delta_css_pixels,
        resolution,
      ),
    );
  };
  target.addEventListener("wheel", handleWheelNavigation, {
    capture: true,
    passive: false,
  });

  const fit = () => {
    map.updateSize();
    view.fit(extent, {
      padding: [28, 28, 28, 28],
      nearest: true,
      duration: 0,
    });
  };

  const featureAtImagePoint = (imageX: number, imageY: number) => {
    const scale = screenPixelsPerImagePixel(view.getResolution() ?? 1);
    let nearest: { feature: IllustratedMapFeatureV1; distance: number } | null = null;
    for (const mapFeature of manifest.features) {
      if (!mapFeature.interaction.selectable) {
        continue;
      }
      const [featureX, featureY] = mapFeature.geometry.coordinates;
      const distance = Math.hypot(imageX - featureX, imageY - featureY);
      const minimumPointerRadiusInImagePixels = 12 / scale;
      const hitRadius = Math.max(
        mapFeature.interaction.hit_radius_image_pixels,
        minimumPointerRadiusInImagePixels,
      );
      if (distance <= hitRadius && (!nearest || distance < nearest.distance)) {
        nearest = { feature: mapFeature, distance };
      }
    }
    return nearest?.feature ?? null;
  };

  const keys: EventsKey[] = [];
  keys.push(
    map.on("singleclick", (event) => {
      const selected = featureAtImagePoint(event.coordinate[0], height - event.coordinate[1]);
      onSelect(selected?.feature_id ?? null);
    }),
  );
  keys.push(
    map.on("pointermove", (event) => {
      if (event.dragging) {
        return;
      }
      const feature = featureAtImagePoint(event.coordinate[0], height - event.coordinate[1]);
      map.getTargetElement().style.cursor = feature ? "pointer" : "grab";
    }),
  );

  const initialFrame = requestAnimationFrame(fit);

  return {
    fit,
    setSelection(featureId) {
      selectedFeatureId = featureId && featuresById.has(featureId) ? featureId : null;
      vectorLayer.changed();
    },
    destroy() {
      cancelAnimationFrame(initialFrame);
      target.removeEventListener("wheel", handleWheelNavigation, true);
      unByKey(keys);
      map.dispose();
    },
  };
}

export default function AtlasViewportImpl(props: AtlasViewportProps) {
  const targetRef = useRef<HTMLDivElement>(null);
  const runtimeRef = useRef<AtlasRuntime | null>(null);
  const onSelectRef = useRef(props.on_select);
  onSelectRef.current = props.on_select;

  useEffect(() => {
    const target = targetRef.current;
    if (!target) {
      return;
    }
    const runtime = createAtlasRuntime(target, props, (featureId) => {
      onSelectRef.current(featureId);
    });
    runtimeRef.current = runtime;
    return () => {
      runtimeRef.current = null;
      runtime.destroy();
    };
  }, [props.manifest, props.raster_url]);

  useEffect(() => {
    runtimeRef.current?.setSelection(props.selected_feature_id);
  }, [props.selected_feature_id]);

  useEffect(() => {
    if (props.fit_request > 0) {
      runtimeRef.current?.fit();
    }
  }, [props.fit_request]);

  return (
    <div
      ref={targetRef}
      className={styles.mapCanvas}
      role="region"
      aria-label={`Interactive map of ${props.manifest.display_name}`}
      aria-describedby="map-instructions"
      tabIndex={0}
    />
  );
}
