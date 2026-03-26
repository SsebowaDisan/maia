import type { ApiSceneState } from "./api/api_scene_state";
import { GenericApiScene } from "./api/scenes/GenericApiScene";
import { resolveSkin } from "./api/skins";

type ApiSceneProps = {
  activeTitle: string;
  state: ApiSceneState;
};

function ApiScene({ activeTitle, state }: ApiSceneProps) {
  const resolved = resolveSkin(state, activeTitle);

  if (resolved) {
    const { Skin, props } = resolved;
    return <Skin {...props} />;
  }

  return <GenericApiScene activeTitle={activeTitle} state={state} />;
}

export { ApiScene };
