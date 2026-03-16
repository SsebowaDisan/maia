import type { ComponentType } from "react";

import { LensEquationWidget, type LensWidgetProps } from "./LensEquationWidget";
import { GenericJsonWidget } from "./GenericJsonWidget";

type WidgetComponentProps = Record<string, unknown>;
type WidgetComponentMap = Record<string, ComponentType<WidgetComponentProps>>;

const widgetRegistry: WidgetComponentMap = {
  lens_equation: LensEquationWidget as ComponentType<WidgetComponentProps>,
  json: GenericJsonWidget as ComponentType<WidgetComponentProps>,
};

function registerWidget(kind: string, component: ComponentType<WidgetComponentProps>) {
  const normalized = String(kind || "").trim().toLowerCase();
  if (!normalized) {
    return;
  }
  widgetRegistry[normalized] = component;
}

function resolveWidget(kind: string): ComponentType<WidgetComponentProps> | null {
  const normalized = String(kind || "").trim().toLowerCase();
  if (!normalized) {
    return null;
  }
  return widgetRegistry[normalized] || null;
}

export { registerWidget, resolveWidget, widgetRegistry };
export type { LensWidgetProps, WidgetComponentProps };
