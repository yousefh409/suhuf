"use client";

import { PaperTexture } from "@paper-design/shaders-react";

interface PaperShaderProps {
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Exact replica of the ShaderPaperTexture from the Paper design file.
 * All values extracted via get_jsx from Paper node IDs 376-0 and 8HC-0.
 */
export default function PaperShader({ className, style }: PaperShaderProps) {
  return (
    <PaperTexture
      colorFront="#4E3D25"
      colorBack="#00000000"
      contrast={0.3}
      roughness={0.4}
      fiber={0.3}
      fiberSize={0.2}
      crumples={0.3}
      crumpleSize={0.35}
      folds={0.65}
      foldCount={5}
      fade={0}
      drops={0.2}
      seed={5.8}
      speed={0}
      scale={0.6}
      fit="cover"
      className={className}
      style={{
        backgroundColor: "#FFFEFC",
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        mixBlendMode: "normal",
        opacity: 0.15,
        ...style,
      }}
    />
  );
}
