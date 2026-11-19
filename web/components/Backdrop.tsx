"use client";

// The page backdrop: four rounded shapes drifting behind frosted glass, drawn in one
// WebGL fragment shader. Each shape is a different figure (disc, slab, capsule,
// triangle) and wanders toward random points, so their overlaps never repeat.
// Colours are read from the stylesheet's tokens. The backdrop is decoration: it
// carries no figure and reads no data.
//
// The glass caps luminance (LUMINANCE_CAP), which is what keeps text legible
// wherever a shape drifts. Without WebGL, or if the shader fails on a GPU, the
// stylesheet's static gradient shows and the error goes to the console: a
// decoration must not take a page of results down with it.

import { useEffect, useRef } from "react";

const SHAPES = 4;

/** Tokens the shapes are tinted with, back to front. */
const SHAPE_TOKENS = ["--dusk-top", "--tile-copper", "--accent", "--dusk-top"];

/** How strongly each shape tints the glass, back to front. */
const SHAPE_STRENGTH = [0.9, 0.85, 0.22, 0.7];

//: Relative luminance the glass never exceeds. --muted (0.370) needs a ground
//: at or under 0.043 for 4.5:1; the margin covers the shader's gamma estimate.
const LUMINANCE_CAP = 0.037;

/** Half-width of shader space that a tall screen is widened to. */
const NARROW = 0.9;

/** Backing-store scale. The frost hides the softness, and phones stay cool. */
const MAX_PIXEL_RATIO = 1.25;

const VERTEX = `
attribute vec2 a_position;
void main() {
  gl_Position = vec4(a_position, 0.0, 1.0);
}`;

const FRAGMENT = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif

uniform vec2 u_resolution;
uniform float u_time;
uniform vec3 u_shape[${SHAPES}];
uniform vec3 u_color[${SHAPES}];
uniform float u_strength[${SHAPES}];
uniform vec3 u_base;
uniform vec3 u_frost;
uniform float u_cap;

float hash(vec2 p) {
  vec3 q = fract(vec3(p.xyx) * 0.1031);
  q += dot(q, q.yzx + 33.33);
  return fract((q.x + q.y) * q.z);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x),
    mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x),
    f.y
  );
}

vec2 turn(vec2 p, float a) {
  float c = cos(a);
  float s = sin(a);
  return vec2(c * p.x - s * p.y, s * p.x + c * p.y);
}

float disc(vec2 p, float r) {
  return length(p) - r;
}

float slab(vec2 p, vec2 half_size, float r) {
  vec2 d = abs(p) - half_size + r;
  return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0) - r;
}

float capsule(vec2 p, float half_length, float r) {
  p.x -= clamp(p.x, -half_length, half_length);
  return length(p) - r;
}

float triangle(vec2 p, float r) {
  const float k = 1.7320508;
  p.x = abs(p.x) - r;
  p.y = p.y + r / k;
  if (p.x + k * p.y > 0.0) p = vec2(p.x - k * p.y, -k * p.x - p.y) / 2.0;
  p.x -= clamp(p.x, -2.0 * r, 0.0);
  return -length(p) * sign(p.y);
}

void main() {
  vec2 p = (gl_FragCoord.xy * 2.0 - u_resolution) / u_resolution.y;
  // On a tall screen the shapes shrink, or one would fill a phone.
  p *= max(1.0, ${NARROW.toFixed(1)} * u_resolution.y / u_resolution.x);

  // The glass: a slow ripple that bends the shapes' outlines, then the frost,
  // which scatters each pixel's line of sight.
  float t = u_time * 0.04;
  p += (vec2(noise(p * 1.7 + t), noise(p * 1.7 + 9.2 - t)) - 0.5) * 0.3;
  // Two grains of frost: crystals a few pixels wide, then a fine scatter.
  vec2 crystal = gl_FragCoord.xy * 0.3;
  p += (vec2(noise(crystal), noise(crystal + 31.0)) - 0.5) * 0.07;
  float grain = hash(gl_FragCoord.xy);
  p += (vec2(grain, hash(gl_FragCoord.xy + 71.0)) - 0.5) * 0.17;

  float d[${SHAPES}];
  d[0] = disc(p - u_shape[0].xy, 0.46);
  d[1] = slab(turn(p - u_shape[1].xy, u_shape[1].z), vec2(0.48, 0.36), 0.28);
  d[2] = capsule(turn(p - u_shape[2].xy, u_shape[2].z), 0.3, 0.27);
  d[3] = triangle(turn(p - u_shape[3].xy, u_shape[3].z), 0.26) - 0.22;

  vec3 color = u_base;
  for (int i = 0; i < ${SHAPES}; i++) {
    color = mix(color, u_color[i], smoothstep(0.34, -0.3, d[i]) * u_strength[i]);
  }

  // The glass itself: a milky veil that thickens where light comes through,
  // and a speckle on its surface.
  float lit = dot(color - u_base, vec3(1.0));
  color = mix(color, u_frost, 0.035 + 0.1 * lit + 0.05 * (grain - 0.5));

  // Compress toward the cap instead of clipping, so overlaps keep their depth.
  vec3 linear = pow(color, vec3(2.2));
  float lum = dot(linear, vec3(0.2126, 0.7152, 0.0722));
  linear *= u_cap * (1.0 - exp(-lum / u_cap)) / max(lum, 1e-5);
  gl_FragColor = vec4(pow(linear, vec3(1.0 / 2.2)), 1.0);
}`;

interface Wanderer {
  x: number;
  y: number;
  vx: number;
  vy: number;
  targetX: number;
  targetY: number;
  angle: number;
  spin: number;
  retargetAt: number;
}

function compile(gl: WebGLRenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type);
  if (!shader) throw new Error("backdrop: could not create a shader");
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(`backdrop: ${gl.getShaderInfoLog(shader) ?? "shader did not compile"}`);
  }
  return shader;
}

/** A token's `#rrggbb` value as three 0-1 channels. */
function token(name: string): [number, number, number] {
  const hex = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const match = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex);
  if (!match) throw new Error(`backdrop: ${name} is not a #rrggbb colour`);
  return [1, 2, 3].map((i) => parseInt(match[i], 16) / 255) as [number, number, number];
}

const between = (low: number, high: number): number => low + Math.random() * (high - low);

export function Backdrop() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    try {
      return paint(canvasRef.current);
    } catch (error) {
      console.error(error);
    }
  }, []);

  return <canvas ref={canvasRef} className="backdrop" aria-hidden />;
}

/** Starts the animation on the canvas and returns its cleanup. */
function paint(canvas: HTMLCanvasElement | null): (() => void) | undefined {
  const gl = canvas?.getContext("webgl", { antialias: false, alpha: false, powerPreference: "low-power" });
  if (!canvas || !gl) return;

  const program = gl.createProgram();
  if (!program) return;
  gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERTEX));
  gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAGMENT));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(`backdrop: ${gl.getProgramInfoLog(program) ?? "program did not link"}`);
  }
  gl.useProgram(program);

  // One triangle that covers the viewport.
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const position = gl.getAttribLocation(program, "a_position");
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

  const uniform = (name: string) => gl.getUniformLocation(program, name);
  gl.uniform3fv(uniform("u_color"), SHAPE_TOKENS.flatMap(token));
  gl.uniform1fv(uniform("u_strength"), SHAPE_STRENGTH);
  gl.uniform3fv(uniform("u_base"), token("--paper"));
  gl.uniform3fv(uniform("u_frost"), token("--ink"));
  gl.uniform1f(uniform("u_cap"), LUMINANCE_CAP);
  const uResolution = uniform("u_resolution");
  const uTime = uniform("u_time");
  const uShape = uniform("u_shape");

  // Shader space: y runs -spanY to spanY and x runs -spanX to spanX.
  let spanX = 1;
  let spanY = 1;
  const resize = () => {
    const ratio = Math.min(window.devicePixelRatio || 1, MAX_PIXEL_RATIO);
    canvas.width = Math.max(1, Math.round(canvas.clientWidth * ratio));
    canvas.height = Math.max(1, Math.round(canvas.clientHeight * ratio));
    const aspect = canvas.width / canvas.height;
    spanY = Math.max(1, NARROW / aspect);
    spanX = aspect * spanY;
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.uniform2f(uResolution, canvas.width, canvas.height);
  };
  resize();

  const place = (w: Wanderer, now: number) => {
    w.targetX = between(-spanX, spanX);
    w.targetY = between(-spanY, spanY);
    w.retargetAt = now + between(7, 16);
  };
  const wanderers: Wanderer[] = Array.from({ length: SHAPES }, () => {
    const w: Wanderer = {
      x: between(-spanX, spanX),
      y: between(-spanY, spanY),
      vx: 0,
      vy: 0,
      targetX: 0,
      targetY: 0,
      angle: between(0, Math.PI * 2),
      spin: between(-0.06, 0.06),
      retargetAt: 0,
    };
    place(w, 0);
    return w;
  });

  const shapes = new Float32Array(SHAPES * 3);
  const draw = (seconds: number, dt: number) => {
    wanderers.forEach((w, i) => {
      if (seconds > w.retargetAt) {
        place(w, seconds);
        w.spin = between(-0.06, 0.06);
      }
      // A weak spring with heavy damping: each shape eases toward its point
      // and is usually sent elsewhere before it arrives.
      w.vx += ((w.targetX - w.x) * 0.02 - w.vx * 0.4) * dt;
      w.vy += ((w.targetY - w.y) * 0.02 - w.vy * 0.4) * dt;
      w.x += w.vx * dt;
      w.y += w.vy * dt;
      w.angle += w.spin * dt;
      shapes.set([w.x, w.y, w.angle], i * 3);
    });
    gl.uniform3fv(uShape, shapes);
    gl.uniform1f(uTime, seconds);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  };

  const still = window.matchMedia("(prefers-reduced-motion: reduce)");
  let frame = 0;
  let last = 0;
  const tick = (ms: number) => {
    const seconds = ms / 1000;
    // A hidden tab resumes with a long gap; don't fling the shapes across it.
    draw(seconds, Math.min(seconds - last, 0.05));
    last = seconds;
    frame = requestAnimationFrame(tick);
  };
  const start = () => {
    cancelAnimationFrame(frame);
    if (still.matches) draw(0, 0);
    else frame = requestAnimationFrame(tick);
  };
  const onResize = () => {
    resize();
    if (still.matches) draw(0, 0);
  };

  start();
  canvas.dataset.ready = "";
  window.addEventListener("resize", onResize);
  still.addEventListener("change", start);
  return () => {
    cancelAnimationFrame(frame);
    window.removeEventListener("resize", onResize);
    still.removeEventListener("change", start);
  };
}
