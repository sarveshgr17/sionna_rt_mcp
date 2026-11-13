import React, { createContext, useContext, useState, useEffect, useMemo, ReactNode } from "react";

export interface SceneConfig {
  name: string;
  label: string;
  boundary: string;
  material: string;
  defaultTx: [number, number, number];
  defaultRx: [number, number, number];
  defaultCellSize: number;
  defaultAutoMargin: number;
  description: string;
}

export const SCENE_CONFIGS: Record<string, SceneConfig> = {
  munich: {
    name: "munich",
    label: "Munich (Dense Urban Macro-cell)",
    boundary: "Urban Macro (~1.5 km × 1.2 km)",
    material: "Concrete, Brick, Marble, Metal (ITU BSDF)",
    defaultTx: [0.0, 0.0, 35.0],
    defaultRx: [60.0, 20.0, 1.5],
    defaultCellSize: 15.0,
    defaultAutoMargin: 20.0,
    description: "Munich city center with historic Frauenkirche & St. Peter cathedrals",
  },
  san_francisco: {
    name: "san_francisco",
    label: "San Francisco (Urban Terrain)",
    boundary: "Coastal & Urban Topography (~1.2 km × 0.9 km)",
    material: "Terrain, Concrete & Urban Facades (ITU BSDF)",
    defaultTx: [0.0, 0.0, 50.0],
    defaultRx: [100.0, 50.0, 1.5],
    defaultCellSize: 15.0,
    defaultAutoMargin: 25.0,
    description: "Hilly San Francisco urban terrain and downtown building footprints",
  },
  simple_street_canyon: {
    name: "simple_street_canyon",
    label: "Simple Street Canyon (3GPP UMi)",
    boundary: "3GPP UMi Canyon (~186 m × 121 m)",
    material: "Concrete, Brick, Glass & Ground",
    defaultTx: [-20.0, 0.0, 15.0],
    defaultRx: [20.0, 0.0, 1.5],
    defaultCellSize: 4.0,
    defaultAutoMargin: 10.0,
    description: "Standard 3GPP micro-cell canyon between building facades",
  },
};

const VALID_SCENE_KEYS = Object.keys(SCENE_CONFIGS);
const STORAGE_KEY = "sionna_selected_scene";

interface SceneContextType {
  activeScene: string;
  setActiveScene: (scene: string) => void;
  currentSceneConfig: SceneConfig;
  allScenes: SceneConfig[];
}

const SceneContext = createContext<SceneContextType | undefined>(undefined);

export function SceneProvider({ children }: { children: ReactNode }) {
  const [activeScene, setActiveSceneState] = useState<string>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored && VALID_SCENE_KEYS.includes(stored)) {
        return stored;
      }
    } catch {
      // Fallback for sandboxed localStorage
    }
    return "munich";
  });

  const setActiveScene = (scene: string) => {
    if (VALID_SCENE_KEYS.includes(scene)) {
      setActiveSceneState(scene);
      try {
        localStorage.setItem(STORAGE_KEY, scene);
      } catch {
        // Fallback for sandboxed localStorage
      }
    }
  };

  useEffect(() => {
    // Sync storage if needed
    try {
      localStorage.setItem(STORAGE_KEY, activeScene);
    } catch {
      // Ignore
    }
  }, [activeScene]);

  const currentSceneConfig = useMemo(() => {
    return SCENE_CONFIGS[activeScene] || SCENE_CONFIGS.munich;
  }, [activeScene]);

  const allScenes = useMemo(() => {
    return Object.values(SCENE_CONFIGS);
  }, []);

  return (
    <SceneContext.Provider
      value={{
        activeScene,
        setActiveScene,
        currentSceneConfig,
        allScenes,
      }}
    >
      {children}
    </SceneContext.Provider>
  );
}

export function useActiveScene(): SceneContextType {
  const context = useContext(SceneContext);
  if (!context) {
    throw new Error("useActiveScene must be used within a SceneProvider");
  }
  return context;
}

