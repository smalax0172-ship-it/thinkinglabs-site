// ski-physics.js — VERIFIED FLIGHT ENGINE, extracted byte-for-byte from ski-jumping.html.
// Do not edit the math. Phaser/UI layers consume this; they never re-derive physics.
"use strict";
const G = 9.81;              // m/s^2
const DEG = Math.PI / 180;
const MASS = 75;             // kg (fixed)
const WEIGHT = MASS * G;     // 735.75 N
const TAKEOFF = -3 * DEG;    // launch angle vs horizontal (slight downslope off table)
const DT = 0.01;             // s, integration timestep
// Landing hill: steep slope of angle B1 to a knee at XK, then a flatter outrun (B2).
const B1 = 35 * DEG, B2 = 14 * DEG, XK = 380;

// Lift coefficient: linear rise to stall (~15 deg), then post-stall decay.
function liftCoeff(aDeg){
  const stall = 15, slope = 0.10, clMax = slope * stall; // 1.5 at stall
  if (aDeg <= stall) return slope * aDeg;
  return Math.max(0.2, clMax - 0.05 * (aDeg - stall));
}
// Drag coefficient: parasitic + induced (rises with CL^2), extra penalty past stall.
function dragCoeff(aDeg){
  const cl = liftCoeff(aDeg);
  let cd = 0.42 + 0.22 * cl * cl;
  if (aDeg > 15) cd += 0.04 * (aDeg - 15);
  return cd;
}
function hillY(x){
  if (x <= XK) return -Math.tan(B1) * x;
  return -Math.tan(B1) * XK - Math.tan(B2) * (x - XK);
}
// Local slope of the hill at touchdown (degrees below horizontal).
function hillAngleAt(x){ return (x <= XK ? B1 : B2) / DEG; }
// Success criterion = how well the landing trajectory angle matches the slope.
// Severity is the pure angle mismatch (degrees). Calibrated to the engine's real 0-26 deg range.
function classifyLanding(sev){
  if (sev <= 6)  return 'clean';
  if (sev <= 12) return 'wobble';
  if (sev <= 19) return 'tumble';
  return 'crash';
}
// One short line naming the physics + the variable to fix. In this sim the skier always lands
// too STEEP (a lift deficit), so the fix is always "make more lift" via whichever input is most off.
function verdictFor(inp, res){
  const titles = { clean:'Clean landing', wobble:'Wobble', tumble:'Tumble', crash:'CRASH — ambulance!' };
  let fix;
  if (inp.alpha > 15)      fix = 'you stalled — ease the angle of attack back under 15°';
  else if (inp.alpha < 6)  fix = 'almost no lift — raise the angle of attack toward ~12°';
  else if (inp.A <= 0.52)  fix = 'too little wing — increase the surface area';
  else if (inp.v0 <= 28)   fix = 'too slow — lift grows with v², add launch speed';
  else                     fix = 'a little more lift would flatten the glide — nudge area or speed';
  let line;
  if (res.tier === 'clean')       line = 'Clean — trajectory matched the slope; lift balanced the glide.';
  else if (res.tier === 'wobble') line = 'A touch too steep on touchdown — ' + fix + '.';
  else if (res.tier === 'tumble') line = 'Landed too steep for the slope — ' + fix + '.';
  else                            line = 'Far too steep, big lift deficit — ' + fix + '.';
  return { title: titles[res.tier], line };
}

// Acceleration from the summed forces at a given state.
function accel(st, p){
  const sp = Math.hypot(st.vx, st.vy);
  let ax = 0, ay = -G;                       // gravity
  if (sp > 1e-6){
    const q = 0.5 * p.rho * sp * sp;          // dynamic pressure
    const L = q * p.cl * p.A;                 // lift magnitude
    const D = q * p.cd * p.A;                 // drag magnitude
    const ux = st.vx / sp, uy = st.vy / sp;   // velocity unit
    const nx = -uy, ny = ux;                  // lift unit (perp to velocity, +90deg)
    ax += (D * (-ux) + L * nx) / p.m;
    ay += (D * (-uy) + L * ny) / p.m;
  }
  return { ax, ay };
}
function deriv(s, p){ const a = accel(s, p); return { x: s.vx, y: s.vy, vx: a.ax, vy: a.ay }; }
function step(s, p, dt){
  const k1 = deriv(s, p);
  const s2 = { x:s.x+k1.x*dt/2, y:s.y+k1.y*dt/2, vx:s.vx+k1.vx*dt/2, vy:s.vy+k1.vy*dt/2 };
  const k2 = deriv(s2, p);
  const s3 = { x:s.x+k2.x*dt/2, y:s.y+k2.y*dt/2, vx:s.vx+k2.vx*dt/2, vy:s.vy+k2.vy*dt/2 };
  const k3 = deriv(s3, p);
  const s4 = { x:s.x+k3.x*dt, y:s.y+k3.y*dt, vx:s.vx+k3.vx*dt, vy:s.vy+k3.vy*dt };
  const k4 = deriv(s4, p);
  return {
    x:  s.x  + dt/6*(k1.x +2*k2.x +2*k3.x +k4.x),
    y:  s.y  + dt/6*(k1.y +2*k2.y +2*k3.y +k4.y),
    vx: s.vx + dt/6*(k1.vx+2*k2.vx+2*k3.vx+k4.vx),
    vy: s.vy + dt/6*(k1.vy+2*k2.vy+2*k3.vy+k4.vy),
  };
}

// Run a full flight. Returns trajectory points (with live L/D) and landing distance.
function simulate(inp){
  const p = { m: MASS, A: inp.A, rho: inp.rho, cl: liftCoeff(inp.alpha), cd: dragCoeff(inp.alpha) };
  let s = { x:0, y:0, vx: inp.v0 * Math.cos(TAKEOFF), vy: inp.v0 * Math.sin(TAKEOFF) };
  const pts = [];
  const record = (st) => {
    const sp = Math.hypot(st.vx, st.vy);
    const q = 0.5 * p.rho * sp * sp;
    pts.push({ x:st.x, y:st.y, vx:st.vx, vy:st.vy, sp, L:q*p.cl*p.A, D:q*p.cd*p.A });
  };
  record(s);
  let landX = 0, landY = 0, landVx = 0, landVy = 0, landed = false;
  for (let i=0; i<40000; i++){
    const prev = s;
    s = step(s, p, DT);
    record(s);
    const pa = prev.y - hillY(prev.x);
    const ca = s.y - hillY(s.x);
    if (pa >= 0 && ca < 0 && s.x > 0.1){
      const t = pa / (pa - ca);
      landX = prev.x + t*(s.x - prev.x);
      landY = prev.y + t*(s.y - prev.y);
      landVx = prev.vx + t*(s.vx - prev.vx);   // velocity at the instant of touchdown
      landVy = prev.vy + t*(s.vy - prev.vy);
      landed = true;
      break;
    }
  }
  const dist = Math.hypot(landX, landY);   // distance along the hill from takeoff
  // --- landing-angle success criterion (the three touchdown numbers) ---
  const landAngle = landed ? Math.atan2(-landVy, landVx) / DEG : 0; // 1) skier trajectory angle (deg below horizontal)
  const hillAngle = landed ? hillAngleAt(landX) : 0;                // 2) hill slope angle at touchdown (deg)
  const severity  = landed ? Math.abs(landAngle - hillAngle) : 0;   // 3) mismatch = severity
  const tier      = classifyLanding(severity);
  return { pts, landX, landY, landVx, landVy, landed, dist, p, inp, landAngle, hillAngle, severity, tier };
}

/* ---- export shim (additive only; physics math above is unchanged) ---- */
const SkiPhysics = { G, DEG, MASS, WEIGHT, TAKEOFF, DT, B1, B2, XK,
  liftCoeff, dragCoeff, hillY, hillAngleAt, classifyLanding, verdictFor,
  accel, deriv, step, simulate };
if (typeof module !== 'undefined' && module.exports) module.exports = SkiPhysics;
if (typeof window !== 'undefined') window.SkiPhysics = SkiPhysics;
