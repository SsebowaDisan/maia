import { resolveApiScene } from "./api_scene_registry";
import type { ApiSceneState } from "./api_scene_state";
import { ConnectorCloneScene } from "./scenes/ConnectorCloneScene";
import { GenericApiScene } from "./scenes/GenericApiScene";

type ApiSceneProps = {
  activeTitle: string;
  state: ApiSceneState;
};

function ApiScene({ activeTitle, state }: ApiSceneProps) {
  const selectedScene = resolveApiScene(state);
  if (selectedScene.kind === "clone") {
    return (
      <ConnectorCloneScene
        activeTitle={activeTitle}
        state={state}
        variant={selectedScene.variant}
      />
    );
  }
  return <GenericApiScene activeTitle={activeTitle} state={state} />;
}

export { ApiScene };
