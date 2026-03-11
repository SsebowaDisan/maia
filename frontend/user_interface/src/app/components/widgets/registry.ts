import type { ComponentType } from "react";

import { LensEquationWidget, type LensWidgetProps } from "./LensEquationWidget";

type WidgetComponentMap = {
  lens_equation: ComponentType<LensWidgetProps>;
};

const widgetRegistry: WidgetComponentMap = {
  lens_equation: LensEquationWidget,
};

export { widgetRegistry };
